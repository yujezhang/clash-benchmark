STRINGS = {
    # Startup
    "loading_sources": "正在加载订阅源...",
    "source_loaded": "  {name}: 共 {total} 个节点，{real} 个真实节点（过滤 {filtered} 个信息性节点）",
    "total_nodes": "  合计：{count} 个节点待测试",
    "mihomo_not_found": (
        "错误：未找到 mihomo 二进制文件。\n"
        "请通过以下命令安装：brew install mihomo\n"
        "或使用 --mihomo /path/to/mihomo 指定路径"
    ),
    "no_sources": (
        "未提供任何订阅源。\n"
        "用法：python main.py [文件或URL ...]\n"
        "      python main.py  （默认读取 sources.yaml）"
    ),
    "sources_file_not_found": "错误：找不到订阅配置文件：{path}",

    # Test phases
    "phase_latency": "[{current}/{total}] 正在测试延迟（每节点 {rounds} 轮）...",
    "phase_speed": "[{current}/{total}] 正在测试下载速度...",
    "phase_geo": "[{current}/{total}] 正在查询地理位置...",
    "phase_geo_skip_dead": "  （{dead} 个不可用节点已跳过）",

    # Table headers - airport comparison
    "table_airport_title": "机场综合对比",
    "col_airport": "机场",
    "col_alive": "可用率",
    "col_median_lat": "延迟中位数",
    "col_p95_lat": "P95 延迟",
    "col_jitter": "抖动",
    "col_speed": "速度",

    # Table headers - node detail
    "table_node_title": "节点详情",
    "col_node": "节点",
    "col_src": "来源",
    "col_type": "类型",
    "col_loss": "丢包率",
    "col_region": "地区",

    # Values
    "dead": "不可用",
    "na_blocked": "N/A(已屏蔽)",
    "na": "N/A",

    # Footer
    "caveat": (
        "注意：以上为单次测试结果。"
        "建议在晚高峰（20:00-23:00）期间运行以获得更具代表性的数据。"
        "QoS 限速可能无法被完全检测到。"
    ),

    # Summary
    "summary_tested_at": "测试时间：{time}",

    # Export
    "exported_json": "结果已导出至：{path}",
    "exported_csv": "结果已导出至：{path}",

    # Errors
    "url_download_failed": "警告：下载 {url} 失败：{error}",
    "url_parse_failed": "警告：解析 {url} 内容失败：{error}",
    "mihomo_start_failed": "错误：mihomo 启动失败：{error}",
    "mihomo_timeout": "错误：mihomo 在 {timeout} 秒内未就绪",
}
