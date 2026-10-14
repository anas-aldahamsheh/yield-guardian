"""Check docs/knowledge/pattern_causes.json and render pattern_causes.md from it.

Run from services/api so the API package imports:

    uv --directory services/api run python ../../docs/knowledge/render_pattern_causes.py

It loads the table with the API's own loader (contract and source checks), then checks that
every pattern has an entry, that no hypothesis uses causal wording, that medium confidence
rests on at least two sources and that quotes are at most 125 characters.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import get_args

from yield_guardian.agent.wording import causal_phrases
from yield_guardian.contracts.knowledge import PatternCauses
from yield_guardian.contracts.wafer import WaferLabel
from yield_guardian.knowledge.service import load_pattern_causes

HERE = Path(__file__).resolve().parent
PATTERNS = [p for p in get_args(WaferLabel) if p != "none"]


def check(causes: PatternCauses) -> list[str]:
    """Rules beyond the loader's: every pattern has an entry, wording is not causal."""
    problems: list[str] = []
    for label in PATTERNS:
        if not any(c.label == label for c in causes.causes):
            problems.append(f"no entry for {label}")
    for c in causes.causes:
        if causal_phrases(c.hypothesis):
            problems.append(f"{c.label}: causal wording in {c.hypothesis!r}")
        if c.confidence == "high":
            problems.append(f"{c.label}: high confidence is not used")
        if c.confidence == "medium" and len({q.source_id for q in c.quotes}) < 2:
            problems.append(f"{c.label}: medium confidence needs two sources")
        problems += [
            f"{c.label}: quote over 125 characters" for q in c.quotes if len(q.quote) > 125
        ]
    return problems


def render(causes: PatternCauses) -> str:
    names = {s.source_id: s for s in causes.sources}

    def cite(source_id: str) -> str:
        s = names[source_id]
        return f"{s.authors[0].split()[-1]}{' et al.' if len(s.authors) > 2 else ''}, {s.year}"

    lines = [
        "# Wafer defect patterns: causes associated with them in the literature",
        "",
        "Generated from `pattern_causes.json` by `render_pattern_causes.py`; edit the JSON, "
        "not this file. The API serves the JSON at `GET /api/v1/knowledge/patterns`.",
        "",
        "## How to read it",
        "",
        causes.framing,
        "",
        "Every quote was read on the publisher's or arXiv's page on 2026-10-14 and kept only "
        "when two separate reads returned the same words. Quotes are short spans of longer "
        "sentences. Source details and licences are in [README.md](README.md).",
        "",
        "## Patterns",
        "",
    ]
    for label in PATTERNS:
        lines += [f"### {label}", ""]
        for c in (c for c in causes.causes if c.label == label):
            lines.append(f"- **{c.hypothesis}** Evidence: {c.confidence}.")
            for q in c.quotes:
                lines.append(f'  - "{q.quote}" ({cite(q.source_id)}; {q.location})')
        lines.append("")
    lines += ["## Sources", ""]
    for s in causes.sources:
        link = f"https://doi.org/{s.doi}" if s.doi else s.url
        lines.append(
            f"- `{s.source_id}`: {', '.join(s.authors)}. *{s.title}*. {s.venue}, {s.year}. {link}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    causes = load_pattern_causes(HERE / "pattern_causes.json")  # the API's own checks
    problems = check(causes)
    for p in problems:
        print("problem:", p)
    (HERE / "pattern_causes.md").write_text(render(causes), encoding="utf-8", newline="\n")
    print(f"{len(causes.causes)} causes, {len(causes.sources)} sources, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
