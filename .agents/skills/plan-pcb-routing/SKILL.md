---
name: plan-pcb-routing
description: Plan or execute a complete KiCad PCB routing workflow, including stackup review, package fanout, differential and controlled-impedance nets, power/plane strategy, net coverage, staged routing commands, and final verification. Use for whole-board routing; do not use for a single isolated DRC failure.
---

# Plan PCB Routing

Follow the shared conventions in `docs/agent-workflows/README.md` and the workflow contract in `docs/agent-workflows/routing-plan.md`.

Use `.claude/skills/plan-pcb-routing/SKILL.md` as a detailed technical reference for package heuristics, command flags, stage ordering, and edge cases. Do not blindly inherit Claude tool names, slash-command syntax, GUI assumptions, or plugin-only output formats.

## Inputs

Require an input `.kicad_pcb` path. Accept optional fabrication limits, output directory/prefix, net filters, plane strategy, impedance targets, and matching tolerances.

Determine the mode before acting:

- `plan-only`: inspect and produce commands, but do not generate routed boards.
- `execute`: run the stages and verify each result. Use this only when the user explicitly asks to route, run, modify, or produce an output board.
- `plugin-compatible plan`: use only when the user explicitly asks for output intended for the existing KiCad plugin Claude tab.

For ambiguous requests such as “analyze this board” or “make a routing plan,” use `plan-only`.

## Procedure

### 1. Preflight

1. Read `AGENTS.md` and `CLAUDE.md`.
2. Confirm the board path exists and parse it with the project parser.
3. Report board bounds, copper layers, footprint count, net count, existing segments/vias, and whether routing already exists.
4. Read stackup, net classes, board design rules, and sibling `.kicad_pro` when available.
5. Record fabrication limits from user-provided or verified manufacturer data. Mark unknown limits instead of inventing them.
6. In execute mode, choose fresh stage output paths before the first modifying command. Never overwrite the source board by default.

### 2. Analyze stackup and high-speed requirements

- Inspect whether the stackup is deliberate or an untouched KiCad default.
- Follow `$find-high-speed-nets` for controlled-impedance and fast single-ended nets.
- Follow `$recommend-stackup` when the stackup is missing, generic, or incompatible with required impedance routing.
- In the plan, separate verified interface requirements from assumptions.

### 3. Analyze fanout

- Detect BGA, PGA, LGA, WLCSP, CSP, CGA, QFN, DFN, and QFP packages.
- Calculate actual populated depth and pad pitch.
- Select `bga_fanout.py`, `qfn_fanout.py`, under-pad escape, or no special fanout.
- Calculate via, drill, track, and clearance values against pitch and fabrication floors.

In execute mode:

1. Run each fanout to a fresh output path and capture its log.
2. Parse `JSON_SUMMARY`.
3. Stop on unexplained `failed > 0` or unescaped nets.
4. Use DRC and geometry evidence to retry with a new output path, changing only justified parameters such as escape layers, via geometry, track width, clearance, or escape method.

In plugin-compatible plan mode, choose conservative first-run parameters because the plugin may not perform iterative retries.

### 4. Analyze differential pairs

Follow `$identify-diff-pairs`.

- Separate confirmed, suspected, and false-positive name matches.
- Group only pairs that share compatible parameters.
- Do not enable polarity swapping unless endpoint capability is verified.
- Put differential-pair routing before the general signal pass.

### 5. Analyze power and planes

Follow `$analyze-power-nets` and the project's plane-mapping guidance.

- Classify rails and supply paths.
- Decide which nets use planes, wide traces, or normal traces.
- Assign plane layers with stackup and return-path rationale.
- Keep split domains separate.

Perform mandatory net-coverage reconciliation:

- Every routable net must be claimed by a stage, intentionally left existing, or explicitly deferred.
- A net excluded from one stage must appear in a later stage.
- Plane nets must not silently disappear from fanout or signal-routing coverage.
- Report overlapping or overly broad glob patterns that could route a net twice or join split domains.

### 6. Build the routing sequence

Normally consider this order, omitting stages that are not needed:

1. Package fanout.
2. Fanout/placement cleanup.
3. Differential pairs.
4. Single-ended controlled-impedance nets.
5. General signals and wide-trace power nets.
6. Plane creation and return vias.
7. Disconnected-plane repair.
8. Reconnect blocker nets ripped by repair.
9. Full board review.

For each stage provide:

- Purpose.
- Exact input and output paths.
- Exact command.
- Log path.
- Expected structured summary or success criteria.
- Verification command.
- Evidence-based retry rule.

Do not emit placeholder commands with unexplained values.

### 7. Execute when requested

For every modifying stage:

1. State the input and output path.
2. Run the exact command and capture stdout/stderr.
3. Inspect structured output and run the stage-specific checker.
4. Continue only when mandatory criteria pass.
5. On failure, diagnose from logs and board geometry before retrying.
6. Stop and report infeasibility when placement, layer count, pitch, or fabrication floors prevent a safe route.

Do not retry blindly and do not claim success from router tallies alone.

### 8. Final verification

Follow `$review-routed-board` on the final output.

At minimum require:

- Project DRC at the actual routed clearance.
- Electrical connectivity.
- Orphan-stub checks.
- Zone-aware KiCad DRC when zones exist and `kicad-cli` is available.
- Matching, return-via, and differential-pair checks when applicable.

## Output

For `plan-only`, return:

1. Board and stackup summary.
2. Assumptions and unverified external facts.
3. Fanout decisions.
4. Confirmed/suspected differential and controlled-impedance nets.
5. Power/plane strategy.
6. Net-coverage reconciliation.
7. Ordered commands with fresh paths and logs.
8. Per-stage success and retry criteria.
9. Final verification commands.

For `execute`, additionally return:

1. Final board path.
2. Stage result table with input, output, command, log, and status.
3. Retries and parameter changes with evidence.
4. Final PASS/FAIL/WARN review.
5. Remaining failures and next actions.

Do not output plugin-specific `RESULT=` or GUI parameter payloads unless plugin-compatible plan mode was explicitly requested.
