#!/usr/bin/env python3
"""Check the section pointers of the spec tree.

A pointer has the form `file NN, section M` or `file NN section M` (M is `7` or `7.2`).
The script reports:
  P1  a pointer to a section that the file does not have;
  P2  a pointer `section M` with no file, in a numbered file that has no section M.

Usage: check-refs.py TREE
Exit code: 0 when the tree is clean, 1 when a finding exists.
"""
import re
import sys
from pathlib import Path

POINTER = re.compile(r"\bfile (\d{2})(?:,)? sections? (\d+(?:\.\d+)*)(?:(?:,| and| to) (\d+(?:\.\d+)*))?")
LOCAL = re.compile(r"\b[Ss]ections? (\d+(?:\.\d+)*)(?:(?:,| and| to) (\d+(?:\.\d+)*))?")
OTHER = re.compile(r"(file \d{2}|of file|RFC|`docs/|design\.md|README|podcrates|podvm|podnet|podssh|podrunner|HyperShell|manual|paper|chapter)", re.I)
HEADING = re.compile(r"^#{2,4} (\d+(?:\.\d+)*)\.? ")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    tree = Path(sys.argv[1])
    sections: dict[str, set[str]] = {}
    for path in sorted(tree.glob("[0-9][0-9]-*.md")):
        found = set()
        for text in path.read_text(encoding="utf-8").splitlines():
            m = HEADING.match(text)
            if m:
                found.add(m.group(1))
        sections[path.name[:2]] = found
    findings = []
    for path in sorted(tree.glob("*.md")) + sorted(tree.glob("*/*.md")):
        rel = path.relative_to(tree).as_posix()
        for no, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in POINTER.finditer(text):
                number = m.group(1)
                if number not in sections:
                    continue
                for sec in (m.group(2), m.group(3)):
                    if sec and sec not in sections[number]:
                        findings.append(f"P1 {rel}:{no} file {number} has no section {sec}")
            own = rel[:2]
            if own not in sections or "/" in rel:
                continue
            for m in LOCAL.finditer(text):
                before = text[max(0, m.start() - 60):m.start()]
                after = text[m.end():m.end() + 24]
                if OTHER.search(before) or re.match(r"\s*(of|in) ", after):
                    continue
                for sec in (m.group(1), m.group(2)):
                    if sec and sec not in sections[own]:
                        findings.append(f"P2 {rel}:{no} this file has no section {sec}")
    for line in findings:
        print(line)
    print(f"check-refs: {sum(len(v) for v in sections.values())} sections, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
