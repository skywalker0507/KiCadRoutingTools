#!/usr/bin/env python3
"""Standalone wrapper: python py_tools/jlc_dfm_check.py board.kicad_pcb ..."""
from __future__ import annotations

from jlc_dfm.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
