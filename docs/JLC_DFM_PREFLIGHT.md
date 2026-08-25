# JLC DFM preflight

`py_tools/jlc_dfm_check.py` adds a local, machine-readable manufacturing preflight before the official JLCPCB/JLCDFM production gate.

It intentionally reuses `py_router/kicad_parser.py` (`PCBData`, pads, vias, tracks, footprints and board bounds) rather than creating another KiCad parser. The rule/profile separation is inspired by EasyEDA's public `eext-jlc-order-dfm-checker` (reference revision `afd538786d510f537ad4fa47c6329e6a99dc7625`), while the runtime is independent of EasyEDA.

## Usage

```bash
python py_tools/jlc_dfm_check.py board.kicad_pcb --json dfm-result.json
```

With JLC BOM/CPL consistency checks:

```bash
python py_tools/jlc_dfm_check.py board.kicad_pcb \
  --bom production/bom.csv \
  --cpl production/positions.csv \
  --json production/dfm-result.json
```

For a non-1 oz outer copper build, pass `--outer-copper-oz` so the FR4 trace tier is selected correctly.

Exit codes are designed for AI/CI gates: `0` means no hard errors, `2` means a hard DFM error, and `--fail-on-warning` returns `1` when only warnings remain.

## Current coverage

The first integration checks board dimensions/layer count, trace width, different-net track spacing, via drill/outer diameter, PTH annular-ring margin, plated/NPTH slots represented by pad drills, same-net pad spacing, via-in-SMD-pad process metadata, component-drill-inside-SMD-pad semantics (thermal-via substitute warning), and BOM/CPL designator consistency.

The JSON result is deliberately stable and compact: each finding carries a rule id, severity, message, measured/required values when applicable, object identifiers and coordinates. That makes it suitable for Codex/agent production-review steps without screenshots.

## Production-gate boundary

This is **not** a replacement for KiCad DRC or the official JLCDFM/CAM review. In particular, the local tool does not have JLC's proprietary placed-component 3D/body/pin models, so online SMT checks such as body collision, pin-to-pad overlap and connector plug-in-hole/model alignment remain final-gate items.

Factory capabilities also change. Treat the local profile as an early warning rule set, keep project overrides possible, and use the order's real surface finish, solder-mask and assembly parameters in the official final check.
