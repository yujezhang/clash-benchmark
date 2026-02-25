from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Optional

import aiohttp
import yaml

# Base port range to avoid conflicts with default clash port (7890).
_BASE_SOCKS_PORT = 17890
_BASE_API_PORT = 19090
_port_counter = 0
_port_lock = asyncio.Lock() if False else None  # initialised lazily


def _next_port_pair() -> tuple[int, int]:
    """Return (socks_port, api_port) for a new mihomo instance."""
    global _port_counter
    socks = _BASE_SOCKS_PORT + _port_counter * 2
    api = _BASE_API_PORT + _port_counter * 2
    _port_counter += 1
    return socks, api


def find_mihomo(override: Optional[str] = None) -> str:
    """
    Locate the mihomo binary.
    Raises FileNotFoundError with a friendly message if not found.
    """
    if override:
        if os.path.isfile(override) and os.access(override, os.X_OK):
            return override
        raise FileNotFoundError(
            f"Specified mihomo path not found or not executable: {override}"
        )
    path = shutil.which("mihomo")
    if path:
        return path
    raise FileNotFoundError("mihomo")


def _build_config(nodes: list[dict], socks_port: int, api_port: int) -> str:
    """Generate a minimal mihomo YAML config string for the given nodes."""
    # Ensure all node names are strings (safety for yaml serialisation)
    safe_nodes = []
    for n in nodes:
        node = {k: v for k, v in n.items() if not k.startswith("_")}
        node["name"] = str(node.get("name", ""))
        safe_nodes.append(node)

    node_names = [n["name"] for n in safe_nodes]

    config = {
        "mixed-port": socks_port,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "error",
        "external-controller": f"127.0.0.1:{api_port}",
        "dns": {"enable": False},
        "proxies": safe_nodes,
        "proxy-groups": [
            {
                "name": "test-group",
                "type": "select",
                "proxies": node_names,
            }
        ],
        "rules": ["MATCH,test-group"],
    }
    return yaml.dump(config, allow_unicode=True, default_flow_style=False)


class MihomoInstance:
    """
    Manages one mihomo subprocess on dedicated ports.
    Use as an async context manager:

        async with MihomoInstance(nodes, mihomo_bin) as m:
            latency = await m.test_latency("node-name")
    """

    def __init__(self, nodes: list[dict], mihomo_bin: str):
        self.nodes = nodes
        self.mihomo_bin = mihomo_bin
        self.socks_port, self.api_port = _next_port_pair()
        self._work_dir: Optional[str] = None
        self._proc: Optional[subprocess.Popen] = None

    @property
    def socks5_url(self) -> str:
        return f"socks5://127.0.0.1:{self.socks_port}"

    @property
    def api_base(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    async def start(self, ready_timeout: float = 10.0) -> None:
        """Write config, start mihomo, wait until REST API is ready."""
        self._work_dir = tempfile.mkdtemp(
            prefix=f"clash-tester-{uuid.uuid4().hex[:8]}-"
        )
        config_path = os.path.join(self._work_dir, "config.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(_build_config(self.nodes, self.socks_port, self.api_port))

        self._proc = subprocess.Popen(
            [self.mihomo_bin, "-f", config_path, "-d", self._work_dir],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Poll until REST API responds or timeout
        deadline = asyncio.get_event_loop().time() + ready_timeout
        async with aiohttp.ClientSession() as session:
            while asyncio.get_event_loop().time() < deadline:
                try:
                    async with session.get(
                        f"{self.api_base}/version",
                        timeout=aiohttp.ClientTimeout(total=1),
                    ) as resp:
                        if resp.status == 200:
                            return
                except Exception:
                    pass
                await asyncio.sleep(0.2)

        # Timed out — kill process and raise
        self._kill()
        raise TimeoutError(
            f"mihomo did not become ready within {ready_timeout}s "
            f"(ports {self.socks_port}/{self.api_port})"
        )

    async def stop(self) -> None:
        """Terminate mihomo and clean up temp files."""
        self._kill()
        if self._work_dir and os.path.isdir(self._work_dir):
            shutil.rmtree(self._work_dir, ignore_errors=True)

    def _kill(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    async def __aenter__(self) -> "MihomoInstance":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()

    async def test_latency(
        self,
        node_name: str,
        test_url: str = "http://www.gstatic.com/generate_204",
        timeout_ms: int = 5000,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Optional[float]:
        """
        Call mihomo REST API to measure latency for one node.
        Returns latency in ms, or None on timeout/error.
        """
        url = (
            f"{self.api_base}/proxies/{_url_encode(node_name)}/delay"
            f"?url={test_url}&timeout={timeout_ms}"
        )
        close_session = session is None
        if session is None:
            session = aiohttp.ClientSession()
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=(timeout_ms / 1000) + 2)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data.get("delay", 0)) or None
                return None
        except Exception:
            return None
        finally:
            if close_session:
                await session.close()

    async def select_node(self, node_name: str, session: aiohttp.ClientSession) -> bool:
        """Switch test-group to the given node via REST API. Returns True on success."""
        url = f"{self.api_base}/proxies/test-group"
        try:
            async with session.put(
                url,
                json={"name": node_name},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status in (200, 204)
        except Exception:
            return False


def _url_encode(s: str) -> str:
    """Percent-encode a proxy name for use in a URL path segment."""
    from urllib.parse import quote

    return quote(s, safe="")
