---
name: recommend-stackup
description: Review a KiCad PCB stackup, detect default or incomplete data, verify current fabrication-service stackups, calculate manufacturable impedance widths with the project formulas, and recommend signal/plane layers and routing arguments. Read-only; use before impedance routing or time matching.
---

# Recommend Stackup

Follow `docs/agent-workflows/README.md` and `docs/agent-workflows/stackup-review.md`.

Use `.claude/skills/recommend-stackup/SKILL.md` as a technical reference for project APIs and output details. Treat literal `WebSearch` wording as generic web access and prefer primary fabrication-service documentation.

## Inputs

Require an input `.kicad_pcb` path. Accept optional intended fabrication service, board thickness, copper weights, layer count, impedance targets, plane requirements, and known process limits.

This skill is read-only. Do not directly modify the board stackup.

## Procedure

### 1. Read the current stackup

```python
from kicad_parser import parse_kicad_pcb

pcb = parse_kicad_pcb("<board.kicad_pcb>")
for layer in pcb.board_info.stackup:
    print(
        layer.name,
        layer.layer_type,
        layer.thickness,
        layer.epsilon_r,
        layer.material,
    )
```

Also record copper-layer order, board thickness, zones/planes, and existing net classes.

### 2. Judge credibility

Classify the stackup as:

- `DELIBERATE`: values appear internally coherent and fabrication-specific.
- `LIKELY_DEFAULT`: absent stackup or repeated generic dielectric values/thicknesses.
- `INCOMPLETE`: some required layer/material/thickness data is missing.
- `UNKNOWN`: insufficient evidence.

State the verdict prominently. Do not use a likely-default stackup to claim accurate impedance or propagation-time results.

### 3. Gather verified requirements

Use results from `$identify-diff-pairs` and `$find-high-speed-nets` when available. Separate verified impedance targets from name-based guesses.

When a fabrication service is named:

1. Find its current official standard stackup and impedance-control capability data.
2. Record the source and relevant service/board-thickness option.
3. Do not invent core, prepreg, dielectric, copper, or process-floor values.

When no fabrication service is known, present assumptions explicitly and avoid calling the result fabrication-ready.

### 4. Recommend layer roles

Propose signal, GND plane, power plane, and mixed-signal roles with return-path rationale.

Check that high-speed signal layers have an adjacent continuous reference plane and that power/split-plane choices do not break critical return paths.

### 5. Validate impedance geometry

Use the project's impedance functions:

```python
from impedance import calculate_width_for_impedance, calculate_impedance_for_layer
```

For every required target and candidate routing layer:

- Calculate the resulting width.
- Compare it with process floors and available routing space.
- Check differential gap requirements when applicable.
- Mark infeasible geometry and propose a specific alternative such as another standard stackup, routing layer, dielectric spacing, or target review.

Do not present a calculated width as manufacturable when the fabrication constraints are unknown.

### 6. Protect existing routing assumptions

If the accepted stackup differs from the board's current stackup, warn that previously calculated impedance widths and time matching are stale and must be rerun.

## Output

Return:

1. Current stackup table and credibility verdict.
2. Verified requirements and their sources.
3. External fabrication data source and selected service option, when applicable.
4. Recommended stackup and layer-role table.
5. Calculated width per impedance target and routing layer.
6. Manufacturability verdict and infeasible targets.
7. Resulting `--layers`, `--impedance`, and plane-layer arguments.
8. Optional manual KiCad Board Setup guidance.
9. A reminder to rerun impedance- and time-based routing after an accepted change.

Do not edit the board file automatically; the user owns the final fabrication-facing stackup decision.
