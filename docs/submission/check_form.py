"""Check the lablab form texts in form.md against the form's limits.

    python3 docs/submission/check_form.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BANNED = ("revolutionary", "game-changing", "cutting-edge", "seamless", "unleash",
          "groundbreaking", "state-of-the-art", "world-class", "next-generation", "magic")


def block(text: str, name: str) -> str:
    match = re.search(rf"<!-- {name}:start -->\n(.*?)\n<!-- {name}:end -->", text, re.S)
    if not match:
        raise SystemExit(f"missing block {name}")
    return match.group(1).strip()


def main() -> int:
    text = (HERE / "form.md").read_text(encoding="utf-8")
    title, short, long = block(text, "title"), block(text, "short"), block(text, "long")
    tags = [t[2:] for t in block(text, "tags").splitlines() if t.startswith("- ")]
    words = len(long.split())
    checks = [
        (f"title {len(title)} chars <= 60", len(title) <= 60),
        (f"short description {len(short)} chars <= 255", len(short) <= 255),
        (f"long description {words} words in 300..500", 300 <= words <= 500),
        (f"{len(tags)} tags in 5..8", 5 <= len(tags) <= 8),
    ]
    script = (HERE / "video_script.md").read_text(encoding="utf-8")
    for name, body in (("form", text), ("video script", script)):
        found = [w for w in BANNED if w in body.lower()]
        checks.append((f"{name}: no hype words {found}", not found))
    seconds = sum(int(m) for m in re.findall(r"^\| \d+ \| (\d+) \|", script, re.M))
    checks.append((f"video scenes total {seconds} s, about 180", 160 <= seconds <= 200))
    for label, ok in checks:
        print(("ok   " if ok else "FAIL ") + label)
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
