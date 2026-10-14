"""Recount docs/STATUS.md: the progress block at the top and the Done line in the summary."""

import re
from pathlib import Path

STATUS = Path(__file__).resolve().parents[1] / "docs" / "STATUS.md"
ROW = re.compile(r"^\| [A-Z]\d+ \|.*\| (✅|🟡|⏳|⛔|✂️) \|", re.M)
START, END = "<!-- progress:start -->", "<!-- progress:end -->"


def main() -> None:
    text = STATUS.read_text(encoding="utf-8")
    sections = re.split(r"^### ", text, flags=re.M)
    lines = ["| Area | Done | In progress | Not started |", "|---|---|---|---|"]
    totals = {"✅": 0, "🟡": 0, "⏳": 0}
    for section in sections[1:]:
        title = section.splitlines()[0].strip()
        marks = ROW.findall(section)
        if not marks:
            continue
        counts = {m: marks.count(m) for m in totals}
        for m in totals:
            totals[m] += counts[m]
        lines.append(f"| {title} | {counts['✅']} of {len(marks)} | {counts['🟡']} | {counts['⏳']} |")
    n = len(ROW.findall(text))
    done = totals["✅"]
    block = "\n".join(
        [
            START,
            f"## Progress: {done} of {n} done ({round(100 * done / n)}%), "
            f"{totals['🟡']} in progress, {totals['⏳']} not started",
            "",
            *lines,
            END,
        ]
    )
    if START in text:
        text = re.sub(re.escape(START) + r".*?" + re.escape(END), block, text, flags=re.S)
    else:
        text = text.replace("\n| Symbol | Meaning |", f"\n{block}\n\n| Symbol | Meaning |", 1)
    text = re.sub(r"\| Done \| \d+ of \d+ \|", f"| Done | {done} of {n} |", text)
    STATUS.write_text(text, encoding="utf-8")
    print(f"{done} of {n}")


if __name__ == "__main__":
    main()
