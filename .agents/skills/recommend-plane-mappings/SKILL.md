---
name: recommend-plane-mappings
description: Recommend exact power and ground net to copper-layer assignments for the KiCad plugin, preserving split domains and high-speed return paths. Analysis only; return a machine-readable RESULT mapping.
---

# Recommend Plane Mappings

Follow `docs/agent-workflows/README.md` and `docs/agent-workflows/plane-mapping.md`.

Use `.claude/skills/recommend-plane-mappings/SKILL.md` as a detailed technical reference for plane-worthy net selection, stackup rationale, and assignment examples. Do not inherit Claude-specific tool names literally.

## Inputs

Require an input `.kicad_pcb` path. Accept optional power-net analysis, stackup findings, current estimates, and intended signal-layer usage.

This skill is analysis-only. Do not create zones, run `route_planes.py`, or modify the board.

## Procedure

1. Parse the board stackup, copper layers, nets, pad counts, existing zones, and net classes.
2. Follow `$analyze-power-nets` when rail roles or current paths are uncertain.
3. Follow `$recommend-stackup` when layer thickness/order is missing or appears to be the KiCad default.
4. Identify continuous GND reference needs for high-speed signal layers.
5. Select plane-worthy rails from evidence rather than names alone.
6. Keep AGND, PGND, filtered rails, and other intentional domains separate unless the circuit explicitly joins them.
7. Assign only real board nets to real copper layers.
8. State when a layer must be split between multiple rails and warn when critical signals would cross that split.
9. Prefer wide traces over planes for low-current or highly fragmented rails when a plane would damage return paths or consume scarce layers.

## Output

Return:

1. Board and stackup summary.
2. Candidate plane-net table with evidence and warnings.
3. Recommended layer assignments and rationale.
4. Rails that should remain wide traces.
5. Exactly one final machine-readable line:

```text
RESULT=GND:In1.Cu;VCC|+3V3:In2.Cu
```

Use exact net names, `|` between nets sharing one layer, and `;` between assignment groups. Do not add prose after the RESULT line.
