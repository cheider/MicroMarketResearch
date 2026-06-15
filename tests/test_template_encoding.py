"""Guard against UTF-8 mojibake in templates and static UI strings."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = (
    ROOT / "app" / "templates",
    ROOT / "app" / "static" / "js",
)

SCAN_SUFFIXES = {".html", ".js"}

# Common UTF-8-as-Latin1 / double-encoding artifacts (em dash, quotes, etc.).
MOJIBAKE_RE = re.compile(
    r"â€|Ã¢|Γé¼|├ó|â€™|â€œ|â€\x9d|â€“"
)


def _ui_files():
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() in SCAN_SUFFIXES and path.is_file():
                yield path


def test_ui_files_are_utf8_not_utf16_le():
    offenders: list[str] = []
    for path in _ui_files():
        head = path.read_bytes()[:4]
        if len(head) >= 2 and head[1] == 0 and head[0] < 128:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, "UTF-16 LE templates break Flask rendering:\n" + "\n".join(offenders)


def test_ui_files_are_valid_utf8_without_mojibake():
    offenders: list[str] = []
    for path in _ui_files():
        text = path.read_text(encoding="utf-8")
        match = MOJIBAKE_RE.search(text)
        if match:
            rel = path.relative_to(ROOT)
            offenders.append(f"{rel} ({match.group()!r})")
    assert not offenders, "Mojibake found:\n" + "\n".join(offenders)


def test_inventory_dashboard_uses_encoding_safe_null_placeholder(client, app):
    response = client.get("/dashboards/inventory")
    assert response.status_code == 200
    assert b"Days on Hand" in response.data
    assert b"\xc3\xa2\xe2\x82\xac" not in response.data  # UTF-8 bytes for â€
    assert b"&#8212;" in response.data or b"&mdash;" in response.data or b"mdash" in response.data
