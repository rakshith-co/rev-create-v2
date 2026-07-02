#!/usr/bin/env python3
"""Compile backend/formats/*.md into backend/seeds/formats.json.

The .md files are the source of truth — one file per ad format ("skill").
Run this after adding or editing a format:

    python3 backend/formats/build.py
"""
import json
import re
import sys
from pathlib import Path

FORMATS_DIR = Path(__file__).parent
OUT = FORMATS_DIR.parent / "seeds" / "formats.json"

REQUIRED = ["id", "name", "status"]
SECTIONS = {"blueprint": "Blueprint", "negatives": "Negatives",
            "re_adaptation": "Real-estate adaptation"}


def parse(path: Path) -> dict:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        sys.exit(f"{path.name}: missing frontmatter block")
    fm_raw, body = m.groups()

    rec = {}
    for line in fm_raw.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if val.startswith("["):
            rec[key.strip()] = json.loads(val)
        elif re.fullmatch(r"-?\d+(\.\d+)?", val):
            rec[key.strip()] = float(val) if "." in val else int(val)
        else:
            rec[key.strip()] = val

    for key, heading in SECTIONS.items():
        sm = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", body, re.S | re.M)
        if sm:
            rec[key] = sm.group(1).strip()

    missing = [k for k in REQUIRED if k not in rec]
    if missing:
        sys.exit(f"{path.name}: missing required fields {missing}")
    if rec["status"] == "active" and "blueprint" not in rec:
        sys.exit(f"{path.name}: active format has no Blueprint section")
    return rec


def main() -> None:
    files = sorted(p for p in FORMATS_DIR.glob("*.md") if p.name != "README.md")
    formats = [parse(p) for p in files]
    ids = [f["id"] for f in formats]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        sys.exit(f"duplicate format ids: {dupes}")

    formats.sort(key=lambda f: -(f.get("re_relevance") or 0))
    OUT.write_text(json.dumps(
        {"source": "compiled from backend/formats/*.md — edit those files, not this one",
         "count": len(formats), "formats": formats},
        indent=2, ensure_ascii=False) + "\n")
    active = sum(1 for f in formats if f["status"] == "active")
    print(f"compiled {len(formats)} formats ({active} active, {len(formats)-active} draft) -> {OUT}")


if __name__ == "__main__":
    main()
