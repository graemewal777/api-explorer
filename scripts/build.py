#!/usr/bin/env python3
"""Turn the public-apis README tables into site/apis.json.

Only tables whose header is `API | Description | Auth | HTTPS | CORS` are read.
The README also holds a promo table and an MCP-server table with other columns;
those are skipped on purpose.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "vendor" / "public-apis" / "README.md"
OUT = ROOT / "site" / "apis.json"

HEADER_RE = re.compile(r"^\|?\s*API\s*\|\s*Description\s*\|\s*Auth\s*\|\s*HTTPS\s*\|\s*CORS\s*\|?\s*$")
ROW_RE = re.compile(r"^\|\s*\[(?P<name>[^\]]+)\]\((?P<url>[^)\s]+)\s*\)\s*\|(?P<rest>.*)$")

MIN_APIS = 1000
MAX_MALFORMED_RATIO = 0.01


def _clean(cell):
    return cell.strip().strip("`").strip()


def _auth(cell):
    return _clean(cell) or "Unknown"


def _https(cell):
    value = _clean(cell).lower()
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


def _cors(cell):
    value = _clean(cell).lower()
    return {"yes": "Yes", "no": "No"}.get(value, "Unknown")


def parse_readme(text):
    apis = []
    category = None
    in_table = False
    malformed = 0
    ragged = 0
    categories = set()

    for line in text.splitlines():
        if line.startswith("### "):
            category = line[4:].strip()
            in_table = False
            continue

        if HEADER_RE.match(line):
            in_table = True
            continue

        if not in_table:
            continue

        if not line.startswith("|"):
            in_table = False
            continue

        if set(line.replace("|", "").strip()) <= set("-: "):
            continue

        match = ROW_RE.match(line)
        rest = match.group("rest").rstrip() if match else ""
        if rest.endswith("|"):
            rest = rest[:-1]
        cells = rest.split("|") if match else []
        if len(cells) < 4:
            malformed += 1
            continue

        # Upstream rows sometimes carry extra trailing cells. Empty ones are harmless;
        # a non-empty one means the row is ragged, so count it and keep the first four.
        if any(extra.strip() for extra in cells[4:]):
            ragged += 1

        description, auth, https, cors = cells[:4]
        apis.append(
            {
                "name": match.group("name").strip(),
                "url": match.group("url"),
                "description": description.strip(),
                "category": category,
                "auth": _auth(auth),
                "https": _https(https),
                "cors": _cors(cors),
            }
        )
        categories.add(category)

    stats = {"parsed": len(apis), "malformed": malformed, "ragged": ragged, "categories": len(categories)}
    return apis, stats


def check_sanity(stats):
    """Fail loudly if upstream changes the README format under us."""
    total = stats["parsed"] + stats["malformed"]
    if stats["parsed"] < MIN_APIS:
        sys.exit(f"build failed: parsed only {stats['parsed']} APIs (expected at least {MIN_APIS}). README format may have changed.")
    if total and stats["malformed"] / total > MAX_MALFORMED_RATIO:
        sys.exit(f"build failed: {stats['malformed']} of {total} rows were malformed (over {MAX_MALFORMED_RATIO:.0%}).")


def _source_commit(readme_path):
    try:
        result = subprocess.run(
            ["git", "-C", str(readme_path.parent), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--readme", type=Path, default=README)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)

    if not args.readme.exists():
        sys.exit(f"build failed: {args.readme} not found. Run: git submodule update --init")

    apis, stats = parse_readme(args.readme.read_text(encoding="utf-8"))
    check_sanity(stats)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source_commit": _source_commit(args.readme), "count": len(apis), "apis": apis}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"wrote {args.out}: {stats['parsed']} APIs in {stats['categories']} categories, "
        f"{stats['malformed']} malformed rows skipped, {stats['ragged']} ragged rows kept"
    )


if __name__ == "__main__":
    main()
