"""Command line entry for JLC local DFM preflight."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .checker import check_bom_cpl, check_pcb
from .standards import make_jlc_fr4_profile


def _load_parser():
    # This package lives under py_tools/jlc_dfm; engine lives in py_router.
    root = Path(__file__).resolve().parents[2]
    engine = root / "py_router"
    if str(engine) not in sys.path:
        sys.path.insert(0, str(engine))
    from kicad_parser import parse_kicad_pcb  # type: ignore
    return parse_kicad_pcb


def _print_text(report):
    d = report.to_dict()
    s = d["summary"]
    status = "PASS" if s["passed"] else "FAIL"
    print(f"JLC DFM preflight: {status}  errors={s['errors']} warnings={s['warnings']}")
    for finding in d["findings"]:
        loc = finding.get("location")
        where = f" @ ({loc[0]:.3f},{loc[1]:.3f})" if loc else ""
        objs = ", ".join(finding.get("objects", []))
        objtxt = f" [{objs}]" if objs else ""
        print(f"[{finding['severity'].upper():7}] {finding['rule']}{objtxt}{where}: {finding['message']}")


def build_arg_parser():
    p = argparse.ArgumentParser(description="Local JLCPCB-oriented preflight for KiCadRoutingTools")
    p.add_argument("pcb", help="Input .kicad_pcb")
    p.add_argument("--bom", help="Optional JLC BOM CSV")
    p.add_argument("--cpl", help="Optional JLC CPL/position CSV")
    p.add_argument("--outer-copper-oz", type=float, default=1.0, help="Outer copper weight used to select JLC trace rules (default: 1.0)")
    p.add_argument("--json", dest="json_path", help="Write machine-readable report JSON")
    p.add_argument("--quiet", action="store_true", help="Do not print human-readable findings")
    p.add_argument("--fail-on-warning", action="store_true", help="Return exit code 1 when warnings exist (errors return 2)")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    pcb_path = Path(args.pcb)
    if not pcb_path.exists():
        print(f"error: PCB file not found: {pcb_path}", file=sys.stderr)
        return 2
    if bool(args.bom) ^ bool(args.cpl):
        print("error: --bom and --cpl must be supplied together", file=sys.stderr)
        return 2

    parser = _load_parser()
    pcb = parser(str(pcb_path))
    layers = len(getattr(pcb.board_info, "copper_layers", None) or []) or 2
    profile = make_jlc_fr4_profile(layers, args.outer_copper_oz)
    report = check_pcb(pcb, source=str(pcb_path), profile=profile)
    if args.bom and args.cpl:
        check_bom_cpl(args.bom, args.cpl, report)

    if args.json_path:
        Path(args.json_path).write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        _print_text(report)

    if report.errors:
        return 2
    if args.fail_on_warning and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
