from __future__ import annotations

import asyncio
from typing import Callable, Optional

import aiohttp
from aiohttp_socks import ProxyConnector

from .metrics import NodeMetrics

_GEO_URL = "http://ip-api.com/json?fields=status,country,countryCode,city,isp,query"

# ip-api.com free tier: 45 requests/minute → 1 req per 1.35s to be safe
_GEO_INTERVAL = 1.4


async def fetch_geolocation(
    nodes_metrics: list[NodeMetrics],
    socks5_urls: dict[str, str],   # node_name -> socks5_url
    progress_cb: Optional[Callable[[int], None]] = None,
) -> None:
    """
    Fetch IP geolocation for each alive node through its SOCKS5 proxy.
    Results are written into each NodeMetrics in-place.

    socks5_urls: mapping from node name to the socks5 URL of the worker
    that tested it (from speed test phase). For latency-only mode, the
    caller provides a shared socks5 URL.
    """
    # Rate-limit with a semaphore and an asyncio lock to enforce interval
    sem = asyncio.Semaphore(1)
    last_request_time = [0.0]

    async def fetch_one(m: NodeMetrics) -> None:
        if not m.is_alive:
            return
        socks5_url = socks5_urls.get(m.node_name)
        if not socks5_url:
            return

        async with sem:
            # Enforce rate limit
            now = asyncio.get_event_loop().time()
            wait = _GEO_INTERVAL - (now - last_request_time[0])
            if wait > 0:
                await asyncio.sleep(wait)
            last_request_time[0] = asyncio.get_event_loop().time()

            try:
                connector = ProxyConnector.from_url(socks5_url)
                async with aiohttp.ClientSession(
                    connector=connector,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as session:
                    async with session.get(_GEO_URL) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            if data.get("status") == "success":
                                m.exit_ip = data.get("query")
                                m.exit_country = data.get("countryCode")
                                m.exit_city = data.get("city")
                                m.exit_isp = data.get("isp")
            except Exception:
                pass  # Geo lookup failure is non-fatal

        if progress_cb:
            progress_cb(1)

    await asyncio.gather(*[fetch_one(m) for m in nodes_metrics])
