#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("coverage.json")
    totals = json.loads(path.read_text(encoding="utf-8"))["totals"]
    statement = float(totals["percent_statements_covered"])
    branch = float(totals["percent_branches_covered"])
    print(f"statement coverage: {statement:.2f}%")
    print(f"branch coverage: {branch:.2f}%")
    return 0 if statement >= 90 and branch >= 85 else 1


if __name__ == "__main__":
    raise SystemExit(main())
