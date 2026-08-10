---
name: review-routed-board
description: Perform read-only post-route QA on a KiCad PCB with project DRC, electrical connectivity, orphan-stub, zone-aware KiCad DRC, length/time matching, GND return-path, and differential-pair checks, then issue a reproducible PASS/FAIL/WARN sign-off.
---

# Review Routed Board

Follow `docs/agent-workflows/README.md` and `docs/agent-workflows/board-review.md`.

Use `.claude/skills/review-routed-board/SKILL.md` as a technical reference for checker behavior, project APIs, and report examples. Replace Claude slash-command references with matching Codex skills such as `$diagnose-routing-failures`.

## Inputs

Require a routed `.kicad_pcb` path. Accept optional:

- Clearance override for a hand-routed board without a routed-floor `.kicad_pro`.
- Length/time-match groups and tolerances.
- High-speed net classifications and required return-via distances.
- Intended differential-pair parameters.
- Routing logs.

This skill is read-only. Do not repair, reroute, or overwrite the board.

## Procedure

### 1. Establish context

1. Confirm the board exists and parses.
2. Identify the sibling `.kicad_pro`, copper zones, stackup, and routing logs when available.
3. Record the exact board path and all commands/log paths used.

### 2. Run project DRC

```bash
python3 -X utf8 check_drc.py <board.kicad_pcb> \
  2>&1 | tee <review-drc.log>
```

Use the routed clearance floor from the sibling `.kicad_pro` when available. Pass `--clearance` only for a documented reason.

Remember that `check_drc.py` does not fully replace zone-aware KiCad DRC, but its touching-copper overlap findings must not be dismissed solely because KiCad reports zero violations.

### 3. Run electrical connectivity

```bash
python3 -X utf8 check_connected.py <board.kicad_pcb> \
  2>&1 | tee <review-connectivity.log>
```

DRC and connectivity are independent. A clean DRC result does not prove pads are connected, and router success tallies are not authoritative.

### 4. Run orphan-stub checks

```bash
python3 -X utf8 check_orphan_stubs.py <board.kicad_pcb> \
  2>&1 | tee <review-orphans.log>
```

Report dead or dangling copper by net and location when available.

### 5. Run zone-aware KiCad DRC when applicable

When zones or planes exist and `kicad-cli` is available:

```bash
kicad-cli pcb drc <board.kicad_pcb> --refill-zones
```

If the tool is unavailable, mark the check `NOT RUN` and explain the coverage gap.

### 6. Verify length or time matching

When groups and tolerances are known:

- Use `calculate_route_length()` for physical length groups.
- Use `calculate_route_propagation_time_ps()` for time-matched groups.
- Include via-barrel effects when supported by the project APIs and stackup.
- Report spread, tolerance, and worst offender per group.

Do not invent groups or tolerances. Mark the category `UNKNOWN` when requirements cannot be established.

### 7. Verify GND return paths

For verified high-speed nets:

- Count signal vias.
- Consider GND vias and through-hole GND pads as return paths.
- Use the documented distance from `$find-high-speed-nets` or the design requirements.
- Report uncovered signal vias with coordinates and nearest return-path distance.

Do not apply generic thresholds when a verified design target is available.

### 8. Review differential pairs

For confirmed pairs:

- Check gap consistency on shared layers.
- Compare P/N length or skew with the intended tolerance.
- Look for crossings or unapproved polarity changes.
- Report pad swaps and whether the schematic was synchronized.

Do not grade suspected pairs as confirmed.

### 9. Determine sign-off

Use only these result labels:

- `PASS`: check ran and met the requirement.
- `FAIL`: check ran and found a mandatory violation.
- `WARN`: non-blocking concern or incomplete secondary validation.
- `NOT RUN`: required tooling or files were unavailable.
- `UNKNOWN`: the design requirement was not known.

Overall sign-off is `FAIL` when DRC or connectivity contains an unresolved mandatory failure. Do not hide failures behind an aggregate score.

## Output

Return:

1. Input board, sibling project file, exact commands, and log paths.
2. A compact table for project DRC, zone DRC, connectivity, orphan stubs, matching, return paths, and differential pairs.
3. Details for every FAIL and material WARN.
4. Checks not run and tool limitations.
5. Concrete next actions.

When failures require root-cause analysis, recommend `$diagnose-routing-failures` with the board and routing logs. Do not perform an unstructured reroute inside this review.
