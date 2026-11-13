#!/usr/bin/env python3
"""Form checks for the podswarm spec tree. A pass means the form is right. It says nothing about meaning.

Usage: python3 scripts/lint-docs.py [TREE]     (TREE defaults to the parent of this script)
Exit 0 only if every rule holds. Each violation prints FILE:LINE: RULE text.

Rules:
  L1  a Markdown file has at most 500 lines
  L2  no em dash and no en dash
  L3  no ' -- ' and no ' - ' used as a dash, outside code fences and inline code
  L4  no absolute machine path of a home, workspace or temporary directory
  L5  no filler word: simply, just, obviously, of course
  L6  no word of the process list (how the text was made)
  L7  no word of a design that the tree does not have
  L8  every 'file NN' names a file that exists
  L9  the first line of a numbered file is '# N. Title', and its sections are numbered '## N. Title'
  L10 no Markdown link that points outside the tree, except an https URL
"""
import pathlib
import re
import sys

tree = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent
bad = []

PROCESS = [
    r"\bthe author\b", r"\bthis session\b", r"\bfetched on\b", r"\bsecond pass\b", r"\bnot run here\b",
    r"\bsnapshot taken\b", r"\btmp-[a-z]+", r"\brepos\.json\b", r"\bv1\b(?! schema)", r"\bv2\b", r"\bv3\b",
    r"\bwas changed\b", r"\bthe old (?:spec|tree|design|text)\b", r"\bthe review(?:er|ers)?\b",
    r"\bObserved\b", r"\bDocumented\b", r"\bInferred\b", r"\bUnverified\b", r"\bSource:",
]
GONE = [
    r"\btier_min\b", r"\blease_s\b", r"\bsession lease\b", r"\bwatchdog\b", r"\bcoord_hash\b",
    r"\bcanonical JSON\b", r"\bT1[2-9]\b", r"\bresults_one\b", r"`welcome`", r"\bsession_epoch\b",
]
PROCESS_RE = [re.compile(p) for p in PROCESS]
GONE_RE = [re.compile(p) for p in GONE]


def err(path, n, rule, text):
    bad.append(f"{path.relative_to(tree)}:{n}: {rule} {text}")


files = sorted(tree.glob("*.md")) + sorted((tree / "evidence").glob("*.md"))
nums = {f.name[:2] for f in tree.glob("[0-9][0-9]-*.md")}

for f in files:
    lines = f.read_text(encoding="utf-8").splitlines()
    if len(lines) > 500:
        err(f, len(lines), "L1", f"{len(lines)} lines")
    numbered = re.match(r"\d\d-", f.name) is not None
    if numbered and lines:
        if not re.match(r"# \d+\. \S", lines[0]):
            err(f, 1, "L9", "first line is not '# N. Title'")
    fence = False
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if "—" in line or "–" in line:
            err(f, i, "L2", "em or en dash")
        if fence:
            continue
        prose = re.sub(r"`[^`]*`", "``", line)
        quote = prose.lstrip().startswith(">")
        if " -- " in prose or re.search(r"(?<=\S) - (?=\S)", prose):
            err(f, i, "L3", "dash used as punctuation")
        if re.search(r"(^|[\s(\"'=])/(home|Users|workspace|tmp|root)/[A-Za-z]", prose):
            err(f, i, "L4", "absolute machine path")
        if not quote and re.search(r"\b(simply|just|obviously|of course)\b", prose, re.I):
            err(f, i, "L5", "filler word")
        if not quote and f.name != "README.md":
            for r in PROCESS_RE:
                m = r.search(prose)
                if m:
                    err(f, i, "L6", f"process word '{m.group(0)}'")
        for r in GONE_RE:
            m = r.search(line)
            if m:
                err(f, i, "L7", f"word of a design that is gone '{m.group(0)}'")
        for m in re.findall(r"\bfiles? (\d{1,2})\b", prose):
            if m.zfill(2) not in nums:
                err(f, i, "L8", f"file {m} does not exist")
        if numbered and re.match(r"## ", line) and not re.match(r"## \d+\. \S", line):
            err(f, i, "L9", "section heading is not '## N. Title'")
        for m in re.findall(r"\]\(([^)]+)\)", line):
            if not m.startswith("https://") and (m.startswith("/") or m.startswith("..") or m.startswith("file:")):
                err(f, i, "L10", f"link outside the tree: {m}")

if bad:
    print("\n".join(bad))
    print(f"{len(bad)} violations")
    sys.exit(1)
print(f"ok: {len(files)} files, 0 violations")
