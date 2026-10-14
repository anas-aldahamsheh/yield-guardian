"""Fail if development fixtures or mock code reached a production build of the web app.

The fixtures in packages/contracts/fixtures exist only for development and tests. This check
looks for their content in the files that a deployment serves or runs:

- every timestamp in the fixtures (each one is a real SECOM time or the fixture clock, and no
  production file has a reason to contain one);
- every long text value in the fixtures that the web app's own source does not also contain
  (report text, evidence, placeholder notes);
- every WM-811K lot and wafer ID in the fixtures (the product loads these from the API);
- paths of the fixture folder and of the web app's mock layer (bundles, traces and source maps
  name the modules they include).

Text is matched on its longest run of plain characters, because bundlers escape quotes,
backslashes, angle brackets and non-ASCII characters in different ways.

Usage (from the repository root, after `pnpm --filter @yield-guardian/web build`):

    python3 scripts/ci/check_no_fixtures.py apps/web/.next apps/web/public
    python3 scripts/ci/check_no_fixtures.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "packages" / "contracts" / "fixtures"
# Source that legitimately ships: text that also appears here is not evidence of a leak.
SHIPPED_SOURCE = [ROOT / "apps" / "web" / "src", ROOT / "packages" / "contracts" / "src"]
NOT_SHIPPED_PARTS = {"mocks", "__tests__", "__mocks__", "e2e"}

TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
WAFER_ID = re.compile(r"^lot\d+(-\d+)?$")
# Fixtures with no data that could identify them; the ESLint import ban in apps/web guards these.
NO_DATA = {"get_session.json": "the anonymous visitor session: four fields, three of them null"}
SAFE_RUN = re.compile(r"[A-Za-z0-9 ,.;:()\[\]{}%+=_/-]+")
MIN_TEXT = 24
PATH_SENTINELS = ("contracts/fixtures/", "src/mocks/")
# Build folders that are never deployed: caches, logs and generated type declarations.
SKIP_DIRS = {"cache", "trace", "types", "dev", "diagnostics", "node_modules"}
# Mock tooling that must not ship even though it holds no data.
MOCK_FILES = {"mockServiceWorker.js"}
TEXT_SUFFIXES = {
    ".js",
    ".mjs",
    ".cjs",
    ".json",
    ".html",
    ".rsc",
    ".txt",
    ".map",
    ".css",
    ".body",
    ".meta",
    ".svg",
    ".xml",
    "",
}


def strings(node: object) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from strings(item)


def longest_safe_run(text: str) -> str:
    runs = SAFE_RUN.findall(text)
    return max((run.strip() for run in runs), key=len, default="")


def shipped_source_text() -> str:
    parts: list[str] = []
    for base in SHIPPED_SOURCE:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or NOT_SHIPPED_PARTS & set(path.relative_to(base).parts):
                continue
            if ".test." in path.name or ".dev." in path.name or path.name.endswith(".d.ts"):
                continue  # tests, dev-only pages and type declarations never reach a bundle
            try:
                parts.append(path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                continue
    return "\n".join(parts)


def sentinels(fixtures: Path, shipped: str) -> dict[str, set[str]]:
    """Map each fixture file name to the strings whose presence in a build proves a leak."""
    found: dict[str, set[str]] = {}
    for path in sorted(fixtures.glob("*.json")):
        marks: set[str] = set()
        for value in strings(json.loads(path.read_text(encoding="utf-8"))):
            if TIMESTAMP.match(value) or WAFER_ID.match(value):
                marks.add(value)
            elif len(value) >= MIN_TEXT:
                run = longest_safe_run(value)
                if len(run) >= MIN_TEXT and run not in shipped:
                    marks.add(run)
        found[path.name] = marks
    return found


def build_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if root.is_file():
            yield root
            continue
        for path in root.rglob("*"):
            relative = path.relative_to(root).parts
            if SKIP_DIRS & set(relative[:-1]) or not path.is_file():
                continue
            if path.suffix in TEXT_SUFFIXES:
                yield path


def scan(roots: list[Path], marks: dict[str, set[str]]) -> list[str]:
    problems: list[str] = []
    for path in build_files(roots):
        text = path.read_text(encoding="utf-8", errors="replace")
        shown = path.as_posix()
        if path.name in MOCK_FILES:
            problems.append(f"{shown}: mock tooling (generate it only for local mock runs)")
            continue
        for fragment in PATH_SENTINELS:
            if fragment in shown or fragment in text:
                problems.append(f"{shown}: names '{fragment}'")
        for fixture, needles in marks.items():
            hits = sorted(needle for needle in needles if needle in text)
            if hits:
                problems.append(
                    f"{shown}: contains {len(hits)} value(s) from {fixture}, e.g. {hits[0]!r}"
                )
    return problems


def self_test() -> None:
    marks = sentinels(FIXTURES, shipped_source_text())
    blind = sorted(name for name, needles in marks.items() if not needles and name not in NO_DATA)
    assert not blind, f"these fixtures have nothing this check can detect: {blind}"
    stale = sorted(name for name in NO_DATA if marks.get(name))
    assert not stale, f"these fixtures are now detectable; remove them from NO_DATA: {stale}"
    with tempfile.TemporaryDirectory() as tmp:
        build = Path(tmp)
        clean = build / "static" / "chunks" / "clean.js"
        clean.parent.mkdir(parents=True)
        clean.write_text('console.log("no fixture data here", 3030.93)', encoding="utf-8")
        assert scan([build], marks) == [], "a clean build was flagged"
        for fixture in sorted(FIXTURES.glob("*.json")):
            if fixture.name in NO_DATA:
                continue
            data = json.loads(fixture.read_text(encoding="utf-8"))
            # The two ways bundlers inline JSON: a JSON.parse string and an object literal.
            minified = json.dumps(data, separators=(",", ":"), ensure_ascii=True)
            leaked = build / "static" / "chunks" / "leak.js"
            leaked.write_text(f"var a=JSON.parse('{minified}');", encoding="utf-8")
            assert scan([build], marks), f"a build containing {fixture.name} was not flagged"
            leaked.unlink()
        cache = build / "cache" / "webpack" / "x.js"
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps(json.loads((FIXTURES / "get_unit.json").read_text())))
        assert scan([build], marks) == [], "the build cache is not deployed and must be skipped"
        worker = build / "mockServiceWorker.js"
        worker.write_text("/* Mock Service Worker */", encoding="utf-8")
        assert scan([build], marks), "the MSW worker script was not flagged"
    total = sum(len(needles) for needles in marks.values())
    print(
        f"self-test passed: {len(marks)} fixtures, {total} sentinel values; every fixture is "
        f"detectable except {len(NO_DATA)} with no data ({', '.join(sorted(NO_DATA))})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="build folders or files to scan")
    parser.add_argument(
        "--self-test", action="store_true", help="check the checker on the fixtures"
    )
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.paths:
        parser.error("give at least one build folder, or --self-test")
    missing = [str(path) for path in args.paths if not path.exists()]
    if missing:
        print(f"not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    marks = sentinels(FIXTURES, shipped_source_text())
    problems = scan(args.paths, marks)
    if problems:
        print("Development fixtures or mock code reached the production build:", file=sys.stderr)
        for problem in problems[:50]:
            print(f"  {problem}", file=sys.stderr)
        if len(problems) > 50:
            print(f"  ... and {len(problems) - 50} more", file=sys.stderr)
        return 1
    scanned = sum(1 for _ in build_files(args.paths))
    print(f"no fixture content in {scanned} build files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
