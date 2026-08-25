"""Command line entry for JLC local DFM preflight."""
from __future__ import annotations

import argparse
from dataclasses import fields
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from .checker import check_bom_cpl, check_pcb
from .standards import JlcFr4Profile, make_jlc_fr4_profile


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
    status = s["status"].replace("_", " ").upper()
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
    p.add_argument("--profile-json", help="Resolved JlcFr4Profile JSON; records its hash and overrides built-in profile selection")
    p.add_argument("--json", dest="json_path", help="Write machine-readable report JSON")
    p.add_argument("--quiet", action="store_true", help="Do not print human-readable findings")
    p.add_argument("--allow-review-required", action="store_true", help="Return 0 for review-required warnings (default is exit 1; errors remain 2)")
    p.add_argument("--fail-on-warning", action="store_true", help=argparse.SUPPRESS)
    return p


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _tool_identity(root: Path):
    commit = None
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    version_path = root / "VERSION"
    files = [
        root / "py_tools/jlc_dfm/checker.py",
        root / "py_tools/jlc_dfm/geometry.py",
        root / "py_tools/jlc_dfm/model.py",
        root / "py_tools/jlc_dfm/standards.py",
        root / "py_tools/jlc_dfm/cli.py",
        root / "py_router/check_drc.py",
        root / "py_router/kicad_parser.py",
    ]
    return {
        "name": "KiCadRoutingTools JLC DFM preflight",
        "version": version_path.read_text(encoding="utf-8").strip() if version_path.exists() else None,
        "commit": commit,
        "source_sha256": {str(p.relative_to(root)).replace("\\", "/"): _sha256(p) for p in files},
    }


def _load_profile(path: Path, layers: int) -> JlcFr4Profile:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("profile"), dict):
        raw = raw["profile"]
    if not isinstance(raw, dict):
        raise ValueError("profile JSON must be an object or contain an object at 'profile'")
    allowed = {f.name for f in fields(JlcFr4Profile)}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"unknown profile field(s): {', '.join(unknown)}")
    profile = JlcFr4Profile(**raw)
    if profile.layer_count != layers:
        raise ValueError(f"profile layer_count={profile.layer_count} does not match board copper layers={layers}")
    return profile


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
    try:
        profile = (_load_profile(Path(args.profile_json), layers) if args.profile_json
                   else make_jlc_fr4_profile(layers, args.outer_copper_oz))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: invalid --profile-json: {exc}", file=sys.stderr)
        return 2
    report = check_pcb(pcb, source=str(pcb_path), profile=profile)
    root = Path(__file__).resolve().parents[2]
    report.tool = _tool_identity(root)
    if args.profile_json:
        profile_path = Path(args.profile_json).resolve()
        report.inputs["profile"] = {
            "path": str(profile_path), "sha256": _sha256(profile_path),
            "bytes": profile_path.stat().st_size,
        }
    if args.bom and args.cpl:
        check_bom_cpl(args.bom, args.cpl, report)

    if args.json_path:
        Path(args.json_path).write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        _print_text(report)

    if report.errors:
        return 2
    if report.warnings and (args.fail_on_warning or not args.allow_review_required):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
