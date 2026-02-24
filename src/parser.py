import base64
import urllib.request
import urllib.error

import yaml


def _decode_content(raw: bytes) -> str:
    """
    Detect if raw bytes are base64-encoded; if so, decode them.
    Returns the decoded string.
    """
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        text = raw.decode("latin-1").strip()

    # Heuristic: Clash YAML always starts with known keys.
    # If the content doesn't look like YAML, try base64 decoding.
    first_line = text.split("\n")[0].strip()
    looks_like_yaml = any(
        first_line.startswith(k)
        for k in ("port:", "mixed-port:", "proxies:", "mode:", "socks-port:", "#")
    )
    if not looks_like_yaml:
        try:
            decoded = base64.b64decode(text + "==").decode("utf-8")
            return decoded
        except Exception:
            pass
    return text


def load_from_file(path: str) -> list[dict]:
    """
    Load a Clash YAML subscription file from disk.
    Returns the list of proxy dicts from the 'proxies' key.
    Raises FileNotFoundError or yaml.YAMLError on failure.
    """
    with open(path, "rb") as f:
        raw = f.read()
    return _parse_clash_yaml(_decode_content(raw), source=path)


def load_from_url(url: str, timeout: int = 15) -> list[dict]:
    """
    Download a Clash subscription URL and return proxy dicts.
    Raises urllib.error.URLError or yaml.YAMLError on failure.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ClashForWindows/0.20.39",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return _parse_clash_yaml(_decode_content(raw), source=url)


def _parse_clash_yaml(text: str, source: str) -> list[dict]:
    """
    Parse a Clash YAML string and extract the proxies list.
    Raises yaml.YAMLError if parsing fails.
    Raises ValueError if the file has no 'proxies' key.
    """
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Not a valid Clash YAML (not a dict): {source}")
    proxies = data.get("proxies")
    if not proxies:
        raise ValueError(f"No 'proxies' key found in: {source}")
    if not isinstance(proxies, list):
        raise ValueError(f"'proxies' is not a list in: {source}")
    return proxies
