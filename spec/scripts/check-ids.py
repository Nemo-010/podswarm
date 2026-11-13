#!/usr/bin/env python3
"""Check the ids of the spec tree.

Each id family has one home file. A definition is an id that starts a table
row or a bold paragraph in its home file. The script reports:
  C1  a cited id with no definition in its home file;
  C2  an id that its home file defines two times;
  C3  a draft tag (`[X-new: ...]`) that still has no id.

Usage: check-ids.py TREE
Exit code: 0 when the tree is clean, 1 when a finding exists.
"""
import re
import sys
from pathlib import Path

# family -> home file (relative to the tree)
HOMES = {
    "D": "25-decisions.md",
    "K": "26-risks-and-rulings.md",
    "R": "26-risks-and-rulings.md",
    "A": "23-testing.md",
    "B": "23-testing.md",
    "E": "23-testing.md",
    "F": "23-testing.md",
    "M": "23-testing.md",
    "S": "23-testing.md",
    "P": "21-crates.md",
    "V": "21-crates.md",
    "N": "21-crates.md",
    "X": "16-security.md",
    "EV": "evidence/facts.md",
}
# words that look like an id and are not one
NOT_IDS = {"P-256", "P-384", "P-521", "X-25519"}

CITE = re.compile(r"(?<![A-Za-z0-9-])(EV|[ABDEFKMNPRSVX])-(\d{1,3})(?![0-9A-Za-z])")
DEFN = re.compile(
    r"^(?:\|\s*|\*\*|#{2,4}\s+)(?:\[)?(EV|[ABDEFKMNPRSVX])-(\d{1,3})(?![0-9A-Za-z])"
)
DRAFT = re.compile(r"\[(?:D|R|E|K|test)-new\b[^\]]*\]")
FENCE = re.compile(r"^\s*```")


def norm(family: str, number: str) -> str:
    return f"{family}-{int(number)}"


def lines_of(path: Path):
    """Yield (line number, text) outside code fences."""
    in_fence = False
    for no, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE.match(text):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield no, text


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    tree = Path(sys.argv[1])
    files = sorted(tree.glob("*.md")) + sorted((tree / "evidence").glob("*.md"))
    defined: dict[str, list[str]] = {}
    for family, home in HOMES.items():
        path = tree / home
        if not path.exists():
            continue
        for no, text in lines_of(path):
            m = DEFN.match(text)
            if m and m.group(1) == family:
                defined.setdefault(norm(*m.groups()), []).append(f"{home}:{no}")
    findings = []
    for ident, places in sorted(defined.items()):
        if len(places) > 1:
            findings.append(f"C2 {ident} defined {len(places)} times: {', '.join(places)}")
    for path in files:
        rel = path.relative_to(tree).as_posix()
        for no, text in lines_of(path):
            for m in DRAFT.finditer(text):
                findings.append(f"C3 {rel}:{no} draft tag {m.group(0)[:60]}")
            for m in CITE.finditer(text):
                if m.group(0) in NOT_IDS:
                    continue
                family = m.group(1)
                home = HOMES[family]
                if not (tree / home).exists():
                    continue
                ident = norm(*m.groups())
                if ident not in defined:
                    findings.append(f"C1 {rel}:{no} {m.group(0)} has no definition in {home}")
    for line in findings:
        print(line)
    print(f"check-ids: {len(defined)} ids, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
