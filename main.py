from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from typing import Optional

import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TaskProgressColumn, TextColumn

from src.i18n import t, set_locale, detect_system_locale
from src.parser import load_from_file, load_from_url
from src.dedup import filter_real_nodes, deduplicate_names
from src.metrics import NodeMetrics, AirportMetrics
from src.mihomo_manager import find_mihomo, MihomoInstance
from src.tester import TestConfig, run_latency_tests, run_speed_tests
from src.geo import fetch_geolocation
from src.reporter import (
    print_airport_table,
    print_node_table,
    print_footer,
    export_json,
    export_csv,
    console,
)

# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python main.py",
        description="Clash airport speed tester",
    )
    p.add_argument(
        "inputs",
        nargs="*",
        metavar="FILE_OR_URL",
        help="Clash YAML files or subscription URLs to test",
    )
    p.add_argument(
        "--sources",
        default="sources.yaml",
        metavar="PATH",
        help="Path to sources.yaml config (default: sources.yaml)",
    )
    p.add_argument("--no-speed", action="store_true", help="Skip download speed tests")
    p.add_argument("--no-geo", action="store_true", help="Skip IP geolocation")
    p.add_argument(
        "--export",
        choices=["JSON", "CSV"],
        default=None,
        help="Export results to file",
    )
    p.add_argument("--export-file", default=None, metavar="PATH", help="Export file path")
    p.add_argument(
        "--concurrency",
        type=int,
        default=30,
        metavar="N",
        help="Max parallel latency tests (default: 30)",
    )
    p.add_argument(
        "--speed-workers",
        type=int,
        default=5,
        metavar="N",
        help="Parallel speed test workers (default: 5)",
    )
    p.add_argument(
        "--sort-by",
        choices=["latency", "p95", "speed", "name"],
        default="latency",
        help="Sort nodes by field (default: latency)",
    )
    p.add_argument("--filter-dead", action="store_true", help="Hide dead nodes from output")
    p.add_argument(
        "--lang",
        choices=["en", "zh"],
        default=None,
        help="Output language: en or zh (default: auto-detect)",
    )
    p.add_argument(
        "--mihomo",
        default=None,
        metavar="PATH",
        help="Path to mihomo binary (default: auto-detect from PATH)",
    )
    return p


# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------

def _load_sources_yaml(path: str) -> list[dict]:
    """Parse sources.yaml and return list of source dicts."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("sources", [])


def _resolve_inputs(args) -> list[tuple[str, str, str]]:
    """
    Return list of (name, kind, path_or_url).
    Combines CLI positional args and sources.yaml.
    """
    sources: list[tuple[str, str, str]] = []

    if args.inputs:
        for inp in args.inputs:
            if inp.startswith("http://") or inp.startswith("https://"):
                # Use domain as name
                from urllib.parse import urlparse
                name = urlparse(inp).netloc or inp[:20]
                sources.append((name, "url", inp))
            else:
                name = os.path.splitext(os.path.basename(inp))[0]
                sources.append((name, "file", inp))
    else:
        if os.path.isfile(args.sources):
            for s in _load_sources_yaml(args.sources):
                kind = s.get("type", "file")
                name = s.get("name", "unknown")
                path = s.get("path") or s.get("url", "")
                sources.append((name, kind, path))
        elif args.sources != "sources.yaml":
            console.print(t("sources_file_not_found", path=args.sources), style="red")
            sys.exit(1)

    return sources


# ---------------------------------------------------------------------------
# Main async logic
# ---------------------------------------------------------------------------

async def run(args) -> None:
    enable_speed = not args.no_speed
    enable_geo = not args.no_geo
    total_phases = 1 + (1 if enable_speed else 0) + (1 if enable_geo else 0)

    # Locate mihomo binary
    try:
        mihomo_bin = find_mihomo(args.mihomo)
    except FileNotFoundError:
        console.print(t("mihomo_not_found"), style="bold red")
        sys.exit(1)

    # Resolve input sources
    sources = _resolve_inputs(args)
    if not sources:
        console.print(t("no_sources"), style="yellow")
        sys.exit(1)

    # Load proxies from each source
    console.print(t("loading_sources"))
    airports: list[AirportMetrics] = []
    all_nodes: list[dict] = []          # deduplicated across all sources
    node_to_source: dict[str, str] = {}  # node_name -> airport name

    for name, kind, path in sources:
        try:
            if kind == "url":
                raw_nodes = load_from_url(path)
            else:
                raw_nodes = load_from_file(path)
        except Exception as e:
            console.print(t("url_download_failed", url=path, error=e), style="yellow")
            continue

        real, filtered = filter_real_nodes(raw_nodes)
        console.print(t("source_loaded", name=name, total=len(raw_nodes),
                        real=len(real), filtered=filtered))

        ap = AirportMetrics(name=name, total_nodes=len(real))
        airports.append(ap)

        for node in real:
            node_to_source[str(node.get("name", ""))] = name

        all_nodes.extend(real)

    # Deduplicate names globally across all sources
    all_nodes = deduplicate_names(all_nodes)

    console.print(t("total_nodes", count=len(all_nodes)))

    # Build metrics map
    tested_at = datetime.now()
    metrics_map: dict[str, NodeMetrics] = {}
    for node in all_nodes:
        name = node["name"]
        src_name = node_to_source.get(name, "")
        # Handle renamed duplicates: strip " (N)" suffix for source lookup
        if not src_name:
            base = name.rsplit(" (", 1)[0]
            src_name = node_to_source.get(base, "")
        m = NodeMetrics(
            node_name=name,
            node_type=node.get("type", "unknown"),
            server=str(node.get("server", "")),
            port=int(node.get("port", 0)),
            source_name=src_name,
            tested_at=tested_at,
        )
        metrics_map[name] = m

    config = TestConfig(
        latency_concurrency=args.concurrency,
        speed_workers=args.speed_workers,
        enable_speed=enable_speed,
        enable_geo=enable_geo,
    )

    # --- Phase 1: Latency ---
    current_phase = 1
    console.print()
    console.print(t("phase_latency", current=current_phase, total=total_phases, rounds=config.latency_rounds))
    with Progress(
        SpinnerColumn(),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("latency", total=len(all_nodes))
        await run_latency_tests(
            all_nodes,
            metrics_map,
            mihomo_bin,
            config,
            progress_cb=lambda n: progress.advance(task, n),
        )

    # --- Phase 2: Speed ---
    socks5_urls: dict[str, str] = {}
    if enable_speed:
        current_phase += 1
        console.print(t("phase_speed", current=current_phase, total=total_phases))
        with Progress(
            SpinnerColumn(),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            alive_count = sum(1 for m in metrics_map.values() if m.is_alive)
            task = progress.add_task("speed", total=alive_count)

            # We need socks5 URLs for geo phase; capture them during speed test
            # by running workers and recording their socks5 URLs per node.
            # For simplicity, run one shared mihomo for geo after speed tests.
            await run_speed_tests(
                all_nodes,
                metrics_map,
                mihomo_bin,
                config,
                progress_cb=lambda n: progress.advance(task, n),
            )

    # --- Phase 3: Geolocation ---
    if enable_geo:
        current_phase += 1
        alive_metrics = [m for m in metrics_map.values() if m.is_alive]
        dead_count = len(metrics_map) - len(alive_metrics)
        console.print(t("phase_geo", current=current_phase, total=total_phases))
        if dead_count:
            console.print(t("phase_geo_skip_dead", dead=dead_count))

        # Start one mihomo instance to route geo requests
        async with MihomoInstance(all_nodes, mihomo_bin) as geo_instance:
            geo_socks5_urls = {m.node_name: geo_instance.socks5_url for m in alive_metrics}

            with Progress(
                SpinnerColumn(),
                BarColumn(),
                TaskProgressColumn(),
                TextColumn("{task.completed}/{task.total}"),
                console=console,
            ) as progress:
                task = progress.add_task("geo", total=len(alive_metrics))
                await fetch_geolocation(
                    alive_metrics,
                    geo_socks5_urls,
                    progress_cb=lambda n: progress.advance(task, n),
                )

    # --- Aggregate per-airport stats ---
    node_by_source: dict[str, list[NodeMetrics]] = {ap.name: [] for ap in airports}
    for m in metrics_map.values():
        if m.source_name in node_by_source:
            node_by_source[m.source_name].append(m)

    for ap in airports:
        ap.nodes = node_by_source[ap.name]
        ap.compute_aggregate()

    # --- Output ---
    # Node detail first, airport comparison last so the summary is visible
    # at the bottom of the terminal when execution finishes.
    print_node_table(
        airports,
        enable_speed,
        sort_by=args.sort_by,
        filter_dead=args.filter_dead,
    )
    print_airport_table(airports, enable_speed)
    print_footer(tested_at)

    # --- Export ---
    if args.export:
        ts = tested_at.strftime("%Y%m%d_%H%M%S")
        if args.export == "JSON":
            out_path = args.export_file or f"results_{ts}.json"
            export_json(airports, out_path)
        else:
            out_path = args.export_file or f"results_{ts}.csv"
            export_csv(airports, out_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Set locale before any output
    lang = args.lang or detect_system_locale()
    set_locale(lang)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
