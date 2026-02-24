import re

# Keywords that identify informational pseudo-nodes (traffic/expiry notices).
_INFO_PATTERNS = [
    r"套餐到期",
    r"订阅获取时间",
    r"Traffic Reset",
    r"Expire Date",
    r"Days Left",
    r"\d+(\.\d+)?\s*(G|GB|T|TB)\s*\|",  # e.g. "50.74 G | 500.00 G"
    r"剩余流量",
    r"到期时间",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INFO_PATTERNS]


def is_informational(node: dict) -> bool:
    """Return True if the node looks like a traffic/expiry notice rather than a real proxy."""
    name = node.get("name", "")
    return any(pat.search(name) for pat in _COMPILED)


def filter_real_nodes(nodes: list[dict]) -> tuple[list[dict], int]:
    """
    Filter out informational pseudo-nodes.
    Returns (real_nodes, filtered_count).
    """
    real = [n for n in nodes if not is_informational(n)]
    return real, len(nodes) - len(real)


def deduplicate_names(nodes: list[dict]) -> list[dict]:
    """
    Ensure all proxy names are unique (mihomo rejects duplicate names).
    Appends ' (2)', ' (3)', etc. to duplicates in-place on copies.
    Returns a new list with unique names.
    """
    seen: dict[str, int] = {}
    result = []
    for node in nodes:
        name = node.get("name", "")
        if name not in seen:
            seen[name] = 1
            result.append(dict(node))
        else:
            seen[name] += 1
            new_node = dict(node)
            new_node["name"] = f"{name} ({seen[name]})"
            result.append(new_node)
    return result
