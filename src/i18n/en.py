STRINGS = {
    # Startup
    "loading_sources": "Loading sources...",
    "source_loaded": "  {name}: {total} nodes loaded, {real} real ({filtered} informational filtered)",
    "total_nodes": "  Total: {count} nodes to test",
    "mihomo_not_found": (
        "Error: mihomo binary not found.\n"
        "Install it with: brew install mihomo\n"
        "Or specify the path with: --mihomo /path/to/mihomo"
    ),
    "no_sources": (
        "No input sources provided.\n"
        "Usage: python main.py [FILE_OR_URL ...]\n"
        "       python main.py  (reads sources.yaml by default)"
    ),
    "sources_file_not_found": "Error: sources file not found: {path}",

    # Test phases
    "phase_latency": "[{current}/{total}] Running latency tests ({rounds} rounds each)...",
    "phase_speed": "[{current}/{total}] Running speed tests...",
    "phase_geo": "[{current}/{total}] Fetching geolocation...",
    "phase_geo_skip_dead": "  ({dead} dead nodes skipped)",

    # Table headers - airport comparison
    "table_airport_title": "Airport Comparison",
    "col_airport": "Airport",
    "col_alive": "Alive",
    "col_median_lat": "Median Lat",
    "col_p95_lat": "P95 Lat",
    "col_jitter": "Jitter",
    "col_speed": "Speed",

    # Table headers - node detail
    "table_node_title": "Node Details",
    "col_node": "Node",
    "col_src": "Src",
    "col_type": "Type",
    "col_loss": "Loss",
    "col_region": "Region",

    # Values
    "dead": "DEAD",
    "na_blocked": "N/A(blocked)",
    "na": "N/A",

    # Footer
    "caveat": (
        "Note: Single-session results only. "
        "For peak-hour accuracy, run during 20:00-23:00 local time. "
        "QoS throttling may not be fully detected."
    ),

    # Summary
    "summary_tested_at": "Tested at: {time}",

    # Export
    "exported_json": "Results exported to: {path}",
    "exported_csv": "Results exported to: {path}",

    # Errors
    "url_download_failed": "Warning: failed to download {url}: {error}",
    "url_parse_failed": "Warning: failed to parse content from {url}: {error}",
    "mihomo_start_failed": "Error: failed to start mihomo: {error}",
    "mihomo_timeout": "Error: mihomo did not become ready within {timeout}s",
}
