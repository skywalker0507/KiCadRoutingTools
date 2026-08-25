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

For a non-1 oz outer copper build, pass `--outer-copper-oz` so the FR4 trace tier is selected correctly. A template or CI system can instead pass a reviewed resolved profile with `--profile-json`; unknown fields and a layer-count mismatch fail closed.

Exit codes are designed for AI/CI gates: `0` means pass, `1` means `review_required`, and `2` means a hard DFM error. `--allow-review-required` is an explicit advisory-mode escape hatch; production automation should not use it.

The JSON binds the PCB, BOM, CPL and optional profile by SHA-256, records the KRT commit/version and checker source hashes, and includes a timestamp- and path-independent evidence fingerprint. A warning-bearing report is never labelled `PASS`.

## Current coverage

The integration checks board dimensions/layer count, trace width, different-net track spacing, via drill/outer diameter, PTH annular-ring margin, plated/NPTH slots represented by pad drills, same-net pad copper proximity, via-drill intersection with paste-bearing SMD pads, component-drill/SMD-pad intersection, and BOM/CPL designator consistency.

Pad and drill checks reuse KiCadRoutingTools' authoritative parser/DRC geometry: parser-resolved `size_x/size_y`, residual `rect_rotation`, custom copper polygons and round/slot drill capsules. Composite primitives sharing the same footprint and pad number are one logical pad rather than a spacing-warning family; identical same-net USB-C contacts are retained as non-blocking information.

The JSON result is deliberately stable and compact: each finding carries a rule id, severity, message, measured/required values when applicable, object identifiers and coordinates. It also reports executed-object metrics so an empty finding family can be distinguished from an omitted check. That makes it suitable for Codex/agent production-review steps without screenshots.

## Production-gate boundary

This is **not** a replacement for KiCad DRC or the official JLCDFM/CAM review. Its assembly scope is BOM/CPL designator consistency plus solder-wicking geometry preflight, not full SMT DFM. The local tool does not have JLC's proprietary placed-component 3D/body/pin models, so online SMT checks such as body collision, pin-to-pad overlap and connector plug-in-hole/model alignment remain final-gate items.

Factory capabilities also change. Treat the local profile as an early warning rule set, keep project overrides possible, and use the order's real surface finish, solder-mask and assembly parameters in the official final check.
