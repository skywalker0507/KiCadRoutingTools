# Plane Mapping Workflow

## Purpose

Recommend which power and ground nets deserve copper planes and assign them to suitable copper layers with signal-integrity and manufacturability rationale.

## Inputs

Required: input `.kicad_pcb` path.

Optional: verified power-net analysis, stackup review, intended signal layers, current estimates, and fabrication constraints.

This workflow is analysis-only. It must not create zones or modify the board.

## Procedure

1. Parse the board stackup, copper-layer order, pad counts, existing zones, net classes, and current assignments.
2. Identify ground domains and candidate power rails using connectivity, pad count, current evidence, and the power-net workflow. Do not classify a net as plane-worthy from its name alone.
3. Preserve intentional split domains such as AGND, PGND, and filtered rails. Do not merge nets merely because they have similar voltage names.
4. Assign continuous GND reference planes adjacent to high-speed signal layers where the layer count permits.
5. Place power planes next to GND where useful for return paths and interplane capacitance, while avoiding a split plane as the reference under critical signals.
6. When multiple rails share a layer, state that a split/multi-net plane is required and identify routing/return-path risks.
7. Verify that every proposed layer is a real copper layer and every proposed net exists on the board.
8. Return exact net names and copper-layer names; do not use broad globs in the machine-readable mapping.

## Output contract

Provide:

1. Board and stackup summary.
2. Plane-worthy net table with evidence, pad count/current rationale, and domain warnings.
3. Recommended assignments as exact net lists mapped to one copper layer each.
4. Signal-integrity rationale for every layer.
5. Nets that should remain wide traces instead of planes.
6. A final single-line mapping suitable for the plugin:

```text
RESULT=GND:In1.Cu;VCC|+3V3:In2.Cu
```

Use `|` between nets sharing one layer and `;` between assignment groups.

## Technical reference

Use `.claude/skills/recommend-plane-mappings/SKILL.md` for detailed project heuristics and examples. Treat Claude-specific tool vocabulary as generic capabilities.
