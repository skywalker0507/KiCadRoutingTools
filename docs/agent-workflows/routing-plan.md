# PCB Routing Plan Workflow

## Purpose

Analyze one KiCad PCB and either produce a routing plan or execute that plan through fresh staged output files.

## Inputs

Required:

- Input `.kicad_pcb` path.

Optional:

- Mode: `plan-only` or `execute`.
- Output directory or filename prefix.
- Fabrication limits and intended manufacturer.
- Nets or components to include/exclude.
- Desired layer count, plane strategy, impedance targets, and length/time-match tolerances.
- Permission to use network access for datasheet verification.

If the user does not specify a mode, default to `plan-only` for a request to analyze or plan, and `execute` only when the user explicitly asks to route, run, modify, or produce an output board.

## Required preflight

1. Confirm that the board exists and can be parsed.
2. Report board dimensions, copper layers, footprint count, net count, existing tracks/vias, and whether the board is fresh or partially routed.
3. Read the board stackup and design-rule/net-class values when available.
4. Identify the real DRC floor and fabrication constraints. Mark unknown fabrication limits rather than inventing them.
5. Choose fresh stage output names before modifying the board.

## Analysis phases

### 1. Stackup and signal-integrity readiness

- Determine whether the stackup is deliberate or an untouched KiCad default.
- Identify signals that require controlled impedance or time matching.
- Recommend running the stackup workflow before impedance routing when the stackup is not credible.

### 2. Fanout requirements

- Detect BGA, PGA, LGA, WLCSP, CSP, CGA, QFN, DFN, and QFP packages.
- Calculate actual populated depth and pitch rather than relying only on package names or total pad count.
- Select `bga_fanout.py`, `qfn_fanout.py`, or no dedicated fanout.
- Calculate via, drill, track, and clearance values against pitch and fabrication floors.
- In execute mode, inspect each fanout `JSON_SUMMARY`; do not continue with unexplained failed or unescaped nets.
- In execute mode, use DRC evidence to retry with smaller feasible geometry, more escape layers, or another escape method.
- In plugin-compatible plan mode, choose conservative parameters that should work on the first run because iterative retry may not occur.

### 3. Differential and controlled-impedance nets

- Follow the differential-pair workflow for confirmed and suspected pairs.
- Follow the high-speed-net workflow for single-ended controlled-impedance nets.
- Route high-priority impedance-controlled nets before the general signal pass.
- Do not enable polarity swapping unless the interface and endpoint capabilities explicitly permit it.

### 4. Power and plane strategy

- Follow the power-net workflow to classify rails, current paths, and widths.
- Decide which nets use planes and which use traces.
- Assign plane layers with return-path and stackup rationale.
- Reconcile net coverage so every routable net is claimed by exactly one intended stage or deliberately deferred.
- Treat split power nets as distinct nets; never merge them into a parent plane merely to satisfy connectivity.

### 5. Routing order

Use evidence from the board, but normally order stages as follows:

1. Package fanout.
2. Fanout/placement cleanup when required.
3. Differential pairs.
4. Single-ended controlled-impedance nets.
5. General signals and wide-trace power nets.
6. Plane creation and return vias.
7. Disconnected-plane repair.
8. Reconnect any blocker nets ripped during repair.
9. Full board review.

Do not emit placeholder steps. Omit stages the board does not need.

## Execute-mode loop

For every modifying stage:

1. State the input board, output board, exact command, and expected success criteria.
2. Run the command and capture stdout/stderr to a uniquely named log.
3. Parse structured summaries when provided.
4. Run the narrow verification appropriate to that stage.
5. Continue only if mandatory criteria pass.
6. On failure, diagnose from logs and board geometry, change one justified parameter set, and route to a new output path.
7. Keep the successful command and parameters in the final reproducibility section.

Do not repeatedly retry blindly. Stop and report the blocking evidence when fabrication floors, layer count, placement, or board geometry make the requested route infeasible.

## Final verification

The final board must be reviewed through the board-review workflow. At minimum:

- DRC at the actual routed clearance.
- Electrical connectivity.
- Orphan/dead stub checks.
- Zone-aware KiCad DRC when zones exist and `kicad-cli` is available.
- Differential-pair, length/time-match, and GND return-via checks when applicable.

## Output contract

### Plan-only output

Provide:

1. Board summary and stackup verdict.
2. Assumptions and unresolved external facts.
3. Package fanout decisions.
4. Confirmed/suspected differential and controlled-impedance nets.
5. Power/plane strategy.
6. A net-coverage summary.
7. Ordered stages with exact input/output paths and commands.
8. Per-stage success criteria and retry guidance.
9. Final verification commands.

### Execute output

Provide:

1. The final output board path.
2. A stage table with command, input, output, result, and log path.
3. Parameters selected and any retries made.
4. Final PASS/FAIL/WARN verification summary.
5. Remaining failures, unverified assumptions, and concrete next actions.

## Technical reference

Use `.claude/skills/plan-pcb-routing/SKILL.md` for detailed package heuristics, command flags, routing stages, and edge cases. Ignore its Claude slash-command syntax and plugin-only behavior unless plugin-compatible plan mode was explicitly requested.
