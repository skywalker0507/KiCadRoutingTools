# Routed Board Review Workflow

## Purpose

Perform read-only post-route QA and produce a reproducible PASS/FAIL/WARN sign-off report.

## Inputs

Required:

- Routed `.kicad_pcb` path.

Optional:

- Explicit clearance override for a hand-routed board without a routed-floor `.kicad_pro`.
- Length- or time-match groups and tolerances.
- High-speed net classifications and GND return-via distances.
- Routing logs and intended differential-pair parameters.

This workflow is read-only. Do not repair or reroute the board unless the user separately asks for changes.

## Required checks

### 1. Project DRC

Run:

```bash
python3 -X utf8 check_drc.py <board.kicad_pcb> 2>&1 | tee <drc-log>
```

Use the routed floor written to the sibling `.kicad_pro` when available. Override clearance only when there is a documented reason.

### 2. Electrical connectivity

Run:

```bash
python3 -X utf8 check_connected.py <board.kicad_pcb> 2>&1 | tee <connectivity-log>
```

Do not infer connectivity from a clean DRC result or the router's own success count.

### 3. Orphan and dead stubs

Run:

```bash
python3 -X utf8 check_orphan_stubs.py <board.kicad_pcb> 2>&1 | tee <orphan-log>
```

### 4. Zone-aware KiCad DRC

When zones or planes exist and `kicad-cli` is available, run:

```bash
kicad-cli pcb drc <board.kicad_pcb> --refill-zones
```

Report the limitation if this check cannot run. A clean KiCad result does not automatically disprove touching-copper overlap findings from the project checker.

### 5. Length and time matching

When groups and tolerances are known:

- Measure route lengths, including via barrels where the project APIs support them.
- For time matching, use the stackup-aware propagation-time function.
- Report spread, tolerance, and worst offender for every group.

Do not invent groups or tolerances. Mark the check `UNKNOWN` when requirements cannot be established.

### 6. GND return paths

For identified high-speed nets:

- Check signal vias against nearby GND vias and through-hole GND pads.
- Use the distance recommended by the high-speed analysis or documented design requirement.
- Report uncovered signal vias with coordinates and nearest return-path distance.

### 7. Differential pairs

Review confirmed differential pairs for:

- Gap consistency on shared layers.
- P/N route length or skew against the intended tolerance.
- Unintended crossings or polarity changes.
- Pad swaps and schematic synchronization requirements.

Do not grade suspected pairs as confirmed without evidence.

## Result semantics

Use these exact categories:

- `PASS`: check ran and met its requirement.
- `FAIL`: check ran and found a mandatory violation.
- `WARN`: non-blocking concern or incomplete secondary validation.
- `NOT RUN`: tooling or files were unavailable.
- `UNKNOWN`: the design requirement was not known.

Overall sign-off is `FAIL` when DRC or connectivity has an unresolved mandatory failure. Do not hide a failure behind an aggregate score.

## Output contract

Provide:

1. Input board, relevant `.kicad_pro`, and exact commands/log paths.
2. A compact result table for DRC, zone DRC, connectivity, orphan stubs, matching, return paths, and differential pairs.
3. Details for every FAIL and material WARN.
4. Tool limitations and checks that were not run.
5. Concrete next actions.

When route or connectivity failures need root-cause analysis, recommend `$diagnose-routing-failures` with the board and routing logs instead of performing an unstructured reroute inside this review.

## Technical reference

Use `.claude/skills/review-routed-board/SKILL.md` for project checker behavior, API examples, and report formatting. Replace Claude slash-command references with the matching Codex skill names.
