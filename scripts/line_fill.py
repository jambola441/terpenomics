#!/usr/bin/env python3
"""
line_fill.py — Kept as a name for catalog_grid.py, which it only calls.

Line fill used to be its own step with its own exceptions (named lines only, line-less
groups by allow-list in data/line_fill.json, no tinctures or topicals, lines curated
"sizes_by_product"). The owner's rule (2026-10-12) replaced all of that: every brand
catalog is a full grid — each group's strains in every size of the group — and every
catalog write keeps it so (catalog_grid.py).

  python scripts/line_fill.py --brand "STIIIZY"     # = catalog_grid.py --brand "STIIIZY"
  python scripts/line_fill.py --all --write         # = catalog_grid.py --all --write
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog_grid import INFERRED, main, plan, sync, sync_brand, wanted  # noqa: E402,F401

if __name__ == "__main__":
    sys.exit(main())
