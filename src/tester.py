from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Optional

import aiohttp
from aiohttp_socks import ProxyConnector

from .metrics import NodeMetrics
from .mihomo_manager import MihomoInstance

# ---------------------------------------------------------------------------
# Speed test URL fallback list
# ---------------------------------------------------------------------------
# Cloudflare has edge PoPs in every major city, so downloads arrive from a
# server near the proxy exit IP — matching how speedtest.net picks its
# nearest server.  This is critical: a UK-only CDN (ThinkBroadband) caps
# Asian-exit proxies at ~30 Mbps due to cross-continent latency, while
# Cloudflare can saturate the proxy's actual bandwidth.
# URLs are tried in order; the first that responds with at least 1 KB of
# real data is used for the full measurement.
_SPEED_URLS: list[str] = [
    "https://speed.cloudflare.com/__down?bytes=100000000",
    "http://cachefly.cachefly.net/100mb.test",
    "http://download.thinkbroadband.com/100MB.zip",
]


@dataclass
class TestConfig:
    latency_url: str = "http://www.gstatic.com/generate_204"
    latency_rounds: int = 10
    latency_timeout_ms: int = 5000
    latency_concurrency: int = 30
    speed_workers: int = 1
    speed_timeout_s: int = 8    # total download duration (seconds)
    speed_connections: int = 16  # parallel TCP connections per measurement
    enable_speed: bool = True
    enable_geo: bool = True


# ---------------------------------------------------------------------------
# Latency testing
# ---------------------------------------------------------------------------

async def run_latency_tests(
    nodes: list[dict],
    metrics_map: dict[str, NodeMetrics],
    mihomo_bin: str,
    config: TestConfig,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> None:
    """
    Load all nodes into one mihomo instance, then measure latency for each
    node with latency_rounds rounds. All (node x round) API calls are fired
    concurrently (limited by semaphore) for maximum throughput.
    """
    async with MihomoInstance(nodes, mihomo_bin) as instance:
        sem = asyncio.Semaphore(config.latency_concurrency)
        round_timeout = config.latency_timeout_ms / 1000 + 5

        # Pre-allocate result slots: node_name -> [None] * rounds
        results: dict[str, list[Optional[float]]] = {
            n["name"]: [None] * config.latency_rounds for n in nodes
        }
        # Track completed rounds per node for progress reporting
        remaining: dict[str, int] = {
            n["name"]: config.latency_rounds for n in nodes
        }

        async def test_one_round(node_name: str, round_idx: int) -> None:
            async with sem:
                try:
                    result = await asyncio.wait_for(
                        instance.test_latency(
                            node_name,
                            test_url=config.latency_url,
                            timeout_ms=config.latency_timeout_ms,
                        ),
                        timeout=round_timeout,
                    )
                except asyncio.TimeoutError:
                    result = None
                results[node_name][round_idx] = result
                remaining[node_name] -= 1
                if remaining[node_name] == 0 and progress_cb:
                    progress_cb(1)

        # Fire all (node x round) tasks concurrently
        tasks = [
            test_one_round(node["name"], r)
            for node in nodes
            for r in range(config.latency_rounds)
        ]
        await asyncio.gather(*tasks)

        # Aggregate results per node
        for node in nodes:
            name = node["name"]
            m = metrics_map[name]
            samples = [v for v in results[name] if v is not None]
            timeouts = config.latency_rounds - len(samples)
            m.latency_samples = samples
            m.latency_loss_rate = timeouts / config.latency_rounds
            m.compute_latency_stats()


# ---------------------------------------------------------------------------
# Speed testing
# ---------------------------------------------------------------------------

async def run_speed_tests(
    nodes: list[dict],
    metrics_map: dict[str, NodeMetrics],
    mihomo_bin: str,
    config: TestConfig,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> None:
    """
    Run download speed tests using a pool of mihomo worker instances.
    Each worker handles one node at a time from a shared queue.
    Only tests alive nodes.
    """
    alive_nodes = [n for n in nodes if metrics_map[n["name"]].is_alive]
    if not alive_nodes:
        return

    queue: asyncio.Queue = asyncio.Queue()
    for node in alive_nodes:
        await queue.put(node)
    for _ in range(config.speed_workers):
        await queue.put(None)

    async def worker() -> None:
        async with MihomoInstance(nodes, mihomo_bin) as instance:
            async with aiohttp.ClientSession() as ctrl_session:
                cached_url: Optional[str] = None
                while True:
                    node = await queue.get()
                    if node is None:
                        break
                    name = node["name"]
                    m = metrics_map[name]
                    # Timeout: probe (~10s worst case) + download + buffer
                    node_timeout = 10 + config.speed_timeout_s + 20
                    try:
                        cached_url = await asyncio.wait_for(
                            _test_node_speed(
                                instance, ctrl_session, name, m, config,
                                cached_url=cached_url,
                            ),
                            timeout=node_timeout,
                        )
                    except asyncio.TimeoutError:
                        pass
                    except asyncio.CancelledError:
                        break
                    finally:
                        if progress_cb:
                            progress_cb(1)

    await asyncio.gather(*[worker() for _ in range(config.speed_workers)])


async def _test_node_speed(
    instance: MihomoInstance,
    ctrl_session: aiohttp.ClientSession,
    name: str,
    m: NodeMetrics,
    config: TestConfig,
    cached_url: Optional[str] = None,
) -> Optional[str]:
    """Switch mihomo to the given node and run a single speed test.
    Returns the working download URL for reuse by subsequent nodes."""
    await instance.select_node(name, ctrl_session)
    await asyncio.sleep(0.3)

    mbps, used_url = await _measure_speed(
        instance.socks5_url,
        _SPEED_URLS,
        config.speed_timeout_s,
        config.speed_connections,
        cached_url=cached_url,
    )
    m.speed_mbps = mbps
    m.speed_blocked = mbps is None
    return used_url


async def _measure_speed(
    socks5_url: str,
    urls: list[str],
    duration_s: int,
    connections: int,
    cached_url: Optional[str] = None,
) -> tuple[Optional[float], Optional[str]]:
    """
    Probe URLs then measure download speed, all through a single shared
    HTTP session so the probe's warm connection can be reused by the
    download phase.  Returns (speed in Mbps, working URL) or
    (None, cached_url) on failure.
    """
    connector = ProxyConnector.from_url(
        socks5_url, limit=connections, limit_per_host=connections,
    )
    timeout = aiohttp.ClientTimeout(sock_connect=15, sock_read=10)

    async with aiohttp.ClientSession(
        connector=connector, timeout=timeout,
    ) as session:
        if cached_url is not None:
            result = await _parallel_speed(session, cached_url, duration_s, connections)
            if result is not None:
                return result, cached_url

        url = await _probe_url(session, urls)
        if url is None:
            return None, cached_url
        result = await _parallel_speed(session, url, duration_s, connections)
        return result, url


async def _probe_url(
    session: aiohttp.ClientSession, urls: list[str],
) -> Optional[str]:
    """
    Try each URL with a small request through the shared session.
    Return the first URL that delivers at least 1 KB of data (to reject
    tiny interception/captcha pages that return HTTP 200).
    """
    probe_timeout = aiohttp.ClientTimeout(total=10, sock_connect=5, sock_read=5)
    for url in urls:
        try:
            async with session.get(url, timeout=probe_timeout) as resp:
                if resp.status in (200, 206):
                    data = await resp.content.read(10240)
                    if len(data) >= 1024:
                        return url
        except BaseException:
            continue
    return None


async def _parallel_speed(
    session: aiohttp.ClientSession,
    url: str,
    duration_s: int,
    connections: int,
) -> Optional[float]:
    """
    Measure aggregate download speed using parallel TCP connections
    through the shared session.  Downloads for duration_s seconds and
    counts all bytes received.  Returns speed in Mbps, or None on failure.
    """
    start = time.monotonic()
    deadline = start + duration_s
    counters = [[0] for _ in range(connections)]

    tasks = [
        asyncio.create_task(
            _download_stream(session, url, deadline, counters[i])
        )
        for i in range(connections)
    ]

    # Tasks self-terminate at deadline. Safety timeout prevents hang.
    try:
        await asyncio.wait(tasks, timeout=duration_s + 15)
    except Exception:
        pass

    # Force-cancel any remaining stuck tasks
    for t in tasks:
        if not t.done():
            t.cancel()
    still_running = [t for t in tasks if not t.done()]
    if still_running:
        try:
            await asyncio.wait(still_running, timeout=5)
        except Exception:
            pass

    elapsed = time.monotonic() - start
    total_bytes = sum(c[0] for c in counters)

    if total_bytes == 0 or elapsed < 0.5:
        return None
    return (total_bytes * 8) / elapsed / 1_000_000


async def _download_stream(
    session: aiohttp.ClientSession, url: str, deadline: float,
    counter: list[int],
) -> None:
    """
    One download loop reusing the shared session until deadline.
    Bytes received are accumulated into counter[0].
    """
    try:
        while time.monotonic() < deadline:
            async with session.get(url) as resp:
                if resp.status >= 400:
                    return
                async for chunk in resp.content.iter_chunked(131072):
                    counter[0] += len(chunk)
                    if time.monotonic() >= deadline:
                        return
    except BaseException:
        pass
