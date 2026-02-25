from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich import box

from .i18n import t
from .metrics import AirportMetrics, NodeMetrics

console = Console()


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _lat_style(ms: Optional[float]) -> Style:
    if ms is None:
        return Style(color="red", bold=True)
    if ms < 100:
        return Style(color="green")
    if ms < 200:
        return Style(color="yellow")
    return Style(color="red")


def _loss_style(rate: float) -> Style:
    if rate == 0:
        return Style(color="white", dim=True)
    if rate < 0.34:
        return Style(color="yellow")
    return Style(color="red")


def _speed_style(mbps: Optional[float]) -> Style:
    if mbps is None:
        return Style(color="white", dim=True)
    if mbps >= 50:
        return Style(color="green")
    if mbps >= 10:
        return Style(color="yellow")
    return Style(color="red")


def _alive_rate_style(rate: float) -> Style:
    if rate >= 0.85:
        return Style(color="green")
    if rate >= 0.60:
        return Style(color="yellow")
    return Style(color="red")


def _jitter_style(ms: Optional[float]) -> Style:
    if ms is None:
        return Style(color="white", dim=True)
    if ms < 30:
        return Style(color="green")
    if ms < 80:
        return Style(color="yellow")
    return Style(color="red")


def _p95_style(ms: Optional[float]) -> Style:
    if ms is None:
        return Style(color="red", bold=True)
    if ms < 200:
        return Style(color="green")
    if ms < 400:
        return Style(color="yellow")
    return Style(color="red")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_ms(ms: Optional[float], dead_label: str) -> str:
    if ms is None:
        return dead_label
    return f"{ms:.0f}ms"


def _fmt_speed(mbps: Optional[float], blocked: bool, na_blocked: str, na: str) -> str:
    if blocked:
        return na_blocked
    if mbps is None:
        return na
    return f"{mbps:.1f} Mbps"


def _fmt_loss(rate: float) -> str:
    if rate == 0:
        return "0%"
    return f"{rate * 100:.0f}%"


def _fmt_jitter(ms: Optional[float]) -> str:
    if ms is None:
        return "-"
    return f"±{ms:.0f}ms"


def _fmt_alive(alive: int, total: int, rate: float) -> str:
    return f"{alive}/{total}  {rate * 100:.1f}%"


def _fmt_region(m: NodeMetrics) -> str:
    parts = []
    if m.exit_country:
        parts.append(m.exit_country)
    if m.exit_city:
        parts.append(m.exit_city)
    if m.exit_isp:
        parts.append(m.exit_isp)
    return "/".join(parts) if parts else "-"


def _src_abbr(name: str) -> str:
    """Return up to 4-char uppercase abbreviation of source name."""
    words = name.split()
    if len(words) >= 2:
        return ("".join(w[0] for w in words[:4])).upper()
    return name[:4].upper()


# ---------------------------------------------------------------------------
# Layer 1: Airport comparison table
# ---------------------------------------------------------------------------

def print_airport_table(airports: list[AirportMetrics], enable_speed: bool) -> None:
    table = Table(
        title=t("table_airport_title"),
        box=box.DOUBLE_EDGE,
        show_header=True,
        header_style="bold cyan",
        title_style="bold white",
    )

    table.add_column(t("col_airport"), style="bold", min_width=12)
    table.add_column(t("col_alive"), justify="right", min_width=12)
    table.add_column(t("col_median_lat"), justify="right", min_width=11)
    table.add_column(t("col_p95_lat"), justify="right", min_width=10)
    table.add_column(t("col_jitter"), justify="right", min_width=8)
    if enable_speed:
        table.add_column(t("col_speed"), justify="right", min_width=13)

    dead_label = t("dead")
    na_blocked = t("na_blocked")
    na = t("na")

    for ap in airports:
        row = [
            ap.name,
            (_fmt_alive(ap.alive_nodes, ap.total_nodes, ap.alive_rate),
             _alive_rate_style(ap.alive_rate)),
            (_fmt_ms(ap.median_latency, dead_label), _lat_style(ap.median_latency)),
            (_fmt_ms(ap.p95_latency, dead_label), _p95_style(ap.p95_latency)),
            (_fmt_jitter(ap.avg_jitter), _jitter_style(ap.avg_jitter)),
        ]
        if enable_speed:
            row.append(
                (_fmt_speed(ap.avg_speed, False, na_blocked, na),
                 _speed_style(ap.avg_speed))
            )

        # rich accepts (text, style) tuples or plain strings
        styled_row = []
        for cell in row:
            if isinstance(cell, tuple):
                from rich.text import Text
                txt = Text(cell[0], style=cell[1])
                styled_row.append(txt)
            else:
                styled_row.append(cell)
        table.add_row(*styled_row)

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Layer 2: Node detail table
# ---------------------------------------------------------------------------

def print_node_table(
    airports: list[AirportMetrics],
    enable_speed: bool,
    sort_by: str = "latency",
    filter_dead: bool = False,
) -> None:
    all_nodes: list[NodeMetrics] = []
    src_abbrs: dict[str, str] = {}
    for ap in airports:
        src_abbrs[ap.name] = _src_abbr(ap.name)
        all_nodes.extend(ap.nodes)

    # Sort: alive first, then by chosen key, dead at bottom
    def sort_key(m: NodeMetrics):
        if not m.is_alive:
            return (1, float("inf"))
        if sort_by == "p95":
            return (0, m.latency_p95 or float("inf"))
        if sort_by == "speed":
            return (0, -(m.speed_mbps or 0))
        if sort_by == "name":
            return (0, m.node_name)
        return (0, m.latency_median or float("inf"))

    all_nodes.sort(key=sort_key)

    if filter_dead:
        all_nodes = [m for m in all_nodes if m.is_alive]

    table = Table(
        title=t("table_node_title"),
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        title_style="bold white",
        show_lines=False,
    )

    table.add_column(t("col_node"), min_width=20, no_wrap=False)
    table.add_column(t("col_src"), min_width=4)
    table.add_column(t("col_type"), min_width=6)
    table.add_column(t("col_median_lat"), justify="right", min_width=8)
    table.add_column(t("col_p95_lat"), justify="right", min_width=8)
    table.add_column(t("col_jitter"), justify="right", min_width=7)
    table.add_column(t("col_loss"), justify="right", min_width=6)
    if enable_speed:
        table.add_column(t("col_speed"), justify="right", min_width=10)
    table.add_column(t("col_region"), min_width=14)

    dead_label = t("dead")
    na_blocked = t("na_blocked")
    na = t("na")

    from rich.text import Text

    for m in all_nodes:
        if m.is_alive:
            median_cell = Text(_fmt_ms(m.latency_median, dead_label), style=_lat_style(m.latency_median))
            p95_cell = Text(_fmt_ms(m.latency_p95, dead_label), style=_p95_style(m.latency_p95))
            jitter_cell = Text(_fmt_jitter(m.latency_jitter), style=_jitter_style(m.latency_jitter))
            loss_cell = Text(_fmt_loss(m.latency_loss_rate), style=_loss_style(m.latency_loss_rate))
        else:
            dead_text = Text(dead_label, style=Style(color="red", bold=True))
            median_cell = dead_text
            p95_cell = Text("-")
            jitter_cell = Text("-")
            loss_cell = Text("100%", style=Style(color="red"))

        row = [
            m.node_name,
            src_abbrs.get(m.source_name, m.source_name[:4]),
            m.node_type,
            median_cell,
            p95_cell,
            jitter_cell,
            loss_cell,
        ]

        if enable_speed:
            if m.is_alive:
                row.append(Text(
                    _fmt_speed(m.speed_mbps, m.speed_blocked, na_blocked, na),
                    style=_speed_style(m.speed_mbps if not m.speed_blocked else None),
                ))
            else:
                row.append(Text("-"))

        row.append(_fmt_region(m))
        table.add_row(*row)

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

def print_footer(tested_at: datetime) -> None:
    console.print()
    console.print(
        t("summary_tested_at", time=tested_at.strftime("%Y-%m-%d %H:%M")),
        style="dim",
    )
    console.print(t("caveat"), style="dim italic")
    console.print()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_json(airports: list[AirportMetrics], path: str) -> None:
    def node_to_dict(m: NodeMetrics) -> dict:
        return {
            "node_name": m.node_name,
            "node_type": m.node_type,
            "server": m.server,
            "port": m.port,
            "source": m.source_name,
            "is_alive": m.is_alive,
            "latency_median_ms": m.latency_median,
            "latency_p95_ms": m.latency_p95,
            "latency_jitter_ms": m.latency_jitter,
            "latency_loss_rate": m.latency_loss_rate,
            "speed_mbps": m.speed_mbps,
            "speed_blocked": m.speed_blocked,
            "exit_ip": m.exit_ip,
            "exit_country": m.exit_country,
            "exit_city": m.exit_city,
            "exit_isp": m.exit_isp,
            "tested_at": m.tested_at.isoformat(),
        }

    def airport_to_dict(ap: AirportMetrics) -> dict:
        return {
            "name": ap.name,
            "total_nodes": ap.total_nodes,
            "alive_nodes": ap.alive_nodes,
            "alive_rate": ap.alive_rate,
            "median_latency_ms": ap.median_latency,
            "p95_latency_ms": ap.p95_latency,
            "avg_jitter_ms": ap.avg_jitter,
            "avg_speed_mbps": ap.avg_speed,
            "nodes": [node_to_dict(n) for n in ap.nodes],
        }

    data = [airport_to_dict(ap) for ap in airports]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    console.print(t("exported_json", path=path), style="dim")


def export_csv(airports: list[AirportMetrics], path: str) -> None:
    fields = [
        "source", "node_name", "node_type", "server", "port",
        "is_alive", "latency_median_ms", "latency_p95_ms",
        "latency_jitter_ms", "latency_loss_rate",
        "speed_mbps", "speed_blocked",
        "exit_ip", "exit_country", "exit_city", "exit_isp", "tested_at",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for ap in airports:
            for m in ap.nodes:
                writer.writerow({
                    "source": m.source_name,
                    "node_name": m.node_name,
                    "node_type": m.node_type,
                    "server": m.server,
                    "port": m.port,
                    "is_alive": m.is_alive,
                    "latency_median_ms": m.latency_median,
                    "latency_p95_ms": m.latency_p95,
                    "latency_jitter_ms": m.latency_jitter,
                    "latency_loss_rate": m.latency_loss_rate,
                    "speed_mbps": m.speed_mbps,
                    "speed_blocked": m.speed_blocked,
                    "exit_ip": m.exit_ip,
                    "exit_country": m.exit_country,
                    "exit_city": m.exit_city,
                    "exit_isp": m.exit_isp,
                    "tested_at": m.tested_at.isoformat(),
                })
    console.print(t("exported_csv", path=path), style="dim")
