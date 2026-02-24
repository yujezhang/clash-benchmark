from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Optional

import aiohttp
from aiohttp_socks import ProxyConnector

from .metrics import NodeMetrics
from .mihomo_manager import MihomoInstance

# Speed test URLs: (label, url, bytes)
_SPEED_URLS = [
    ("intl", "https://speed.cloudflare.com/__down?bytes=10000000", 10_000_000),
    ("domestic", "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb", 10_000_000),
]


@dataclass
class TestConfig:
    latency_url: str = "http://www.gstatic.com/generate_204"
    latency_rounds: int = 10
    latency_timeout_ms: int = 5000
    latency_concurrency: int = 30
    speed_workers: int = 5
    speed_timeout_s: int = 20
    enable_speed: bool = True
    enable_geo: bool = True


async def run_latency_tests(
    nodes: list[dict],
    metrics_map: dict[str, NodeMetrics],
    mihomo_bin: str,
    config: TestConfig,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> None:
    """
    Load all nodes into one mihomo instance, then measure latency for each node
    using the REST API with latency_rounds rounds per node.
    Results are written into metrics_map in-place.
    """
    async with MihomoInstance(nodes, mihomo_bin) as instance:
        sem = asyncio.Semaphore(config.latency_concurrency)

        async def test_one(node: dict) -> None:
            name = node["name"]
            async with sem:
                async with aiohttp.ClientSession() as session:
                    samples: list[float] = []
                    timeouts = 0
                    for _ in range(config.latency_rounds):
                        result = await instance.test_latency(
                            name,
                            test_url=config.latency_url,
                            timeout_ms=config.latency_timeout_ms,
                            session=session,
                        )
                        if result is not None:
                            samples.append(result)
                        else:
                            timeouts += 1

                    m = metrics_map[name]
                    m.latency_samples = samples
                    m.latency_loss_rate = timeouts / config.latency_rounds
                    m.compute_latency_stats()

            if progress_cb:
                progress_cb(1)

        await asyncio.gather(*[test_one(n) for n in nodes])


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

    # Sentinel values to stop workers
    for _ in range(config.speed_workers):
        await queue.put(None)

    async def worker() -> None:
        async with MihomoInstance(nodes, mihomo_bin) as instance:
            async with aiohttp.ClientSession() as ctrl_session:
                while True:
                    node = await queue.get()
                    if node is None:
                        break
                    name = node["name"]
                    m = metrics_map[name]
                    await instance.select_node(name, ctrl_session)
                    await asyncio.sleep(0.3)  # brief settle time after switching

                    for label, url, expected_bytes in _SPEED_URLS:
                        mbps = await _measure_speed(
                            instance.socks5_url,
                            url,
                            expected_bytes,
                            config.speed_timeout_s,
                        )
                        blocked = mbps is None and await _is_blocked(
                            instance.socks5_url, url, config.speed_timeout_s
                        )
                        if label == "intl":
                            m.speed_intl_mbps = mbps
                            m.speed_intl_blocked = blocked
                        else:
                            m.speed_domestic_mbps = mbps
                            m.speed_domestic_blocked = blocked

                    if progress_cb:
                        progress_cb(1)

    await asyncio.gather(*[worker() for _ in range(config.speed_workers)])


async def _measure_speed(
    socks5_url: str,
    url: str,
    expected_bytes: int,
    timeout_s: int,
) -> Optional[float]:
    """
    Download up to expected_bytes through socks5_url proxy.
    Performs two downloads and returns the lower Mbps value (QoS detection).
    Returns None on connection failure.
    """
    results = []
    for _ in range(2):
        mbps = await _single_download(socks5_url, url, expected_bytes, timeout_s)
        if mbps is None:
            return None
        results.append(mbps)
    return min(results)


async def _single_download(
    socks5_url: str,
    url: str,
    max_bytes: int,
    timeout_s: int,
) -> Optional[float]:
    """Download through proxy, return Mbps or None on failure."""
    try:
        connector = ProxyConnector.from_url(socks5_url)
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=timeout_s),
        ) as session:
            start = time.monotonic()
            received = 0
            async with session.get(url) as resp:
                if resp.status >= 400:
                    return None
                async for chunk in resp.content.iter_chunked(65536):
                    received += len(chunk)
                    if received >= max_bytes:
                        break
            elapsed = time.monotonic() - start
            if elapsed < 0.1 or received == 0:
                return None
            return (received * 8) / elapsed / 1_000_000  # Mbps
    except Exception:
        return None


async def _is_blocked(socks5_url: str, url: str, timeout_s: int) -> bool:
    """
    Return True if the URL is reachable through the proxy but returns
    an error (blocked), vs not reachable at all.
    """
    try:
        connector = ProxyConnector.from_url(socks5_url)
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=min(timeout_s, 10)),
        ) as session:
            async with session.head(url) as resp:
                # Reachable but blocked (e.g. 403/451/connection reset)
                return resp.status >= 400
    except aiohttp.ClientResponseError:
        return True
    except Exception:
        return False
