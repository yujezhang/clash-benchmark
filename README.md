# Clash Benchmark

[English](#english) | [中文](#中文)

---

<p align="center">
  <img src="demo.gif" alt="Clash Benchmark Demo" width="1000">
</p>

---

## 中文

### 项目简介

Clash 机场性能基准测试工具：一键对比多个机场延迟（Median/P95/Jitter）、带宽吞吐及节点可用率。

### 前置条件

- Python 3.10+
- **mihomo**（必须安装）：
  ```bash
  brew install mihomo   # macOS
  ```
  其他平台请参考 [mihomo 官方文档](https://github.com/MetaCubeX/mihomo)

- Python 依赖：
  ```bash
  pip3 install -r requirements.txt
  ```

### 快速开始

```bash
# 直接测试本地订阅文件
python main.py /path/to/airport-a.yaml /path/to/airport-b.yaml

# 直接测试订阅链接
python main.py https://airport-a.com/subscribe/abc123def456 https://airport-b.com/subscribe/abc123def456

# 混合使用（文件 + 链接）
python main.py /path/to/airport-a.yaml https://airport-b.com/subscribe/abc123def456

# 仅测延迟（更快）
python main.py /path/to/airport.yaml --no-speed

# 中文输出
python main.py /path/to/airport.yaml --lang zh

# 使用 sources.yaml 管理多个订阅源（推荐）
cp sources.yaml.example sources.yaml
# 编辑 sources.yaml，填入你的订阅信息
python main.py
```

### sources.yaml 配置

推荐将订阅来源写入 `sources.yaml`，统一管理多个订阅：

```yaml
sources:
  - name: airport-a
    type: file
    path: /path/to/airport-a.yaml

  - name: airport-b
    type: url
    url: https://airport-b.com/subscribe/abc123def456
```

### 完整用法

```
python main.py [FILE_OR_URL ...] [OPTIONS]

选项：
  --sources PATH        指定订阅配置文件（默认：sources.yaml）
  --no-speed            跳过下载速度测试
  --no-geo              跳过 IP 地理位置查询
  --export JSON|CSV     导出结果文件
  --export-file PATH    导出文件路径
  --concurrency N       并发延迟测试数（默认：30）
  --speed-workers N     并发速度测试 worker 数（默认：5）
  --sort-by FIELD       节点排序字段：latency|p95|speed|name（默认：latency）
  --filter-dead         隐藏不可用节点
  --lang en|zh          输出语言（默认：自动检测）
  --mihomo PATH         手动指定 mihomo 二进制路径
```

### 测试方法说明

| 指标 | 测试方法 |
|------|---------|
| 延迟中位数 | 通过 mihomo REST API 对每个节点测试 10 轮，取中位数 |
| P95 延迟 | 10 轮测试的第 95 百分位，反映"偶尔卡顿"的情况 |
| 抖动 | 10 轮延迟的标准差，反映稳定性 |
| 丢包率 | 10 轮中超时的比例 |
| 国际速度 | 通过节点下载 Cloudflare 测速文件（10MB），测两次取低值 |
| 国内速度 | 通过节点下载国内可访问文件（10MB），测两次取低值 |
| 地理位置 | 通过节点请求 ip-api.com 获取出口 IP 信息 |

> **注意**：本工具为单次测试，结果受测试时间影响。建议在晚高峰（20:00-23:00）运行，以获得更具代表性的数据。QoS 限速可能无法被完全检测到（通过同一 URL 测速两次取低值可部分识别）。

---

## English

### Overview

Clash airport benchmarking tool: compare multiple subscriptions in one run — latency (Median/P95/Jitter), throughput, and node availability.

### Prerequisites

- Python 3.10+
- **mihomo** (required):
  ```bash
  brew install mihomo   # macOS
  ```
  For other platforms, see [mihomo releases](https://github.com/MetaCubeX/mihomo)

- Python dependencies:
  ```bash
  pip3 install -r requirements.txt
  ```

### Quick Start

```bash
# Test a local subscription file
python main.py /path/to/airport-a.yaml /path/to/airport-b.yaml

# Test a subscription URL directly
python main.py https://airport-a.com/subscribe/abc123def456 https://airport-b.com/subscribe/abc123def456

# Mix files and URLs
python main.py /path/to/airport-a.yaml https://example.com/airport-b/abc123def456

# Latency only (faster)
python main.py /path/to/airport.yaml --no-speed

# English output
python main.py /path/to/airport.yaml --lang en

# Use sources.yaml for multiple subscriptions (recommended)
cp sources.yaml.example sources.yaml
# Edit sources.yaml with your subscription details
python main.py
```

### sources.yaml Configuration

Store your subscription sources in `sources.yaml` to manage multiple subscriptions in one place:

```yaml
sources:
  - name: airport-a
    type: file
    path: /path/to/airport-a.yaml

  - name: airport-b
    type: url
    url: https://airport-b.com/subscribe/abc123def456
```

> `sources.yaml` is listed in `.gitignore` and will not be committed.

### Full Usage

```
python main.py [FILE_OR_URL ...] [OPTIONS]

Options:
  --sources PATH        Sources config file (default: sources.yaml)
  --no-speed            Skip download speed tests
  --no-geo              Skip IP geolocation
  --export JSON|CSV     Export results to file
  --export-file PATH    Export file path
  --concurrency N       Max parallel latency tests (default: 30)
  --speed-workers N     Parallel speed test workers (default: 5)
  --sort-by FIELD       Sort nodes by: latency|p95|speed|name (default: latency)
  --filter-dead         Hide dead nodes from output
  --lang en|zh          Output language (default: auto-detect)
  --mihomo PATH         Path to mihomo binary
```

### Testing Methodology

| Metric | Method |
|--------|--------|
| Median latency | 10 rounds per node via mihomo REST API, take median |
| P95 latency | 95th percentile of 10 rounds — measures occasional slowness |
| Jitter | Standard deviation of 10 rounds — measures stability |
| Loss rate | Fraction of rounds that timed out |
| International speed | Download 10MB via Cloudflare, twice, report lower value |
| Domestic speed | Download 10MB via domestic-accessible URL, twice, report lower value |
| Geolocation | Request ip-api.com through the node's proxy |

> **Note**: Results are from a single test session and depend on the time of day. For peak-hour accuracy, run during 20:00–23:00 local time. QoS throttling may not be fully detected (downloading twice and taking the lower value provides partial detection).

### Why mihomo?

Modern Shadowsocks ciphers such as `2022-blake3-aes-128-gcm` are not supported by any pure-Python library. `mihomo` (the successor to clash-meta) handles all current proxy protocols natively, making it a hard dependency.
