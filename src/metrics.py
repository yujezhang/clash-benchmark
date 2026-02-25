from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NodeMetrics:
    node_name: str
    node_type: str          # e.g. trojan, ss, vmess
    server: str
    port: int
    source_name: str        # airport name from sources.yaml / CLI arg
    is_alive: bool = False

    # Latency stats (ms). None means not tested / all timed out.
    latency_samples: list[float] = field(default_factory=list, repr=False)
    latency_median: Optional[float] = None
    latency_p95: Optional[float] = None
    latency_jitter: Optional[float] = None   # stddev across samples
    latency_loss_rate: float = 1.0           # 0.0–1.0

    # Speed (Mbps). None = not tested.
    speed_mbps: Optional[float] = None
    speed_blocked: bool = False

    # Geolocation
    exit_ip: Optional[str] = None
    exit_country: Optional[str] = None
    exit_city: Optional[str] = None
    exit_isp: Optional[str] = None

    tested_at: datetime = field(default_factory=datetime.now)

    def compute_latency_stats(self) -> None:
        """Compute median, P95, jitter, loss_rate from latency_samples."""
        total_rounds = max(len(self.latency_samples), 1)
        if not self.latency_samples:
            self.is_alive = False
            self.latency_loss_rate = 1.0
            return

        self.is_alive = True
        sorted_s = sorted(self.latency_samples)
        n = len(sorted_s)

        self.latency_median = statistics.median(sorted_s)

        # P95: 95th percentile
        idx = math.ceil(0.95 * n) - 1
        self.latency_p95 = sorted_s[max(0, idx)]

        self.latency_jitter = statistics.stdev(sorted_s) if n > 1 else 0.0

        # loss_rate is computed by the tester (timeouts / total rounds)
        # kept as-is here


@dataclass
class AirportMetrics:
    name: str
    total_nodes: int = 0
    tested_nodes: int = 0   # nodes actually tested (may differ from total if sampled)
    alive_nodes: int = 0
    nodes: list[NodeMetrics] = field(default_factory=list)

    # Aggregate stats computed from nodes
    alive_rate: float = 0.0
    median_latency: Optional[float] = None   # median of per-node medians
    p95_latency: Optional[float] = None      # median of per-node P95s
    avg_jitter: Optional[float] = None
    avg_speed: Optional[float] = None

    def compute_aggregate(self) -> None:
        """Compute airport-level stats from node metrics."""
        self.tested_nodes = len(self.nodes)
        alive = [n for n in self.nodes if n.is_alive]
        self.alive_nodes = len(alive)
        self.alive_rate = self.alive_nodes / self.tested_nodes if self.tested_nodes else 0.0

        medians = [n.latency_median for n in alive if n.latency_median is not None]
        if medians:
            self.median_latency = statistics.median(medians)

        p95s = [n.latency_p95 for n in alive if n.latency_p95 is not None]
        if p95s:
            self.p95_latency = statistics.median(p95s)

        jitters = [n.latency_jitter for n in alive if n.latency_jitter is not None]
        if jitters:
            self.avg_jitter = statistics.mean(jitters)

        speeds = [
            n.speed_mbps
            for n in alive
            if n.speed_mbps is not None and not n.speed_blocked
        ]
        if speeds:
            self.avg_speed = statistics.mean(speeds)
