# Power Net Analysis Workflow

## Purpose

Identify power and ground nets, trace supply paths, classify component roles, and recommend routing widths or plane treatment.

## Inputs

Required: an input `.kicad_pcb` path.

Optional: known supply voltages, expected load currents, fabrication limits, copper weight, and permission to use network access for datasheet verification.

This workflow is analysis-only unless the user explicitly asks to route power nets.

## Procedure

### 1. Extract local evidence

Run the project power-path analyzer and collect components, values, footprints, net names, pad connectivity, power-pin metadata, existing net classes, and existing planes.

### 2. Classify components

Use deterministic local rules only for obvious passive components. Do not infer an IC, connector, diode, or transistor role from its reference prefix alone.

For every important unknown component:

1. Identify the exact part number or state that it is ambiguous.
2. Prefer an official manufacturer datasheet or reference manual.
3. Record the evidence used, such as supply pins, output rating, supply demand, connector rating, switch topology, or protection topology.
4. Classify it as `POWER_SOURCE`, `CURRENT_SINK`, `PASS_THROUGH`, or `SHUNT`.
5. Record the estimated demand or rating and a confidence level.

When network access is unavailable, use local symbol and connectivity evidence and mark datasheet-dependent values as `UNKNOWN` or `UNVERIFIED`.

### 3. Trace supply paths

Apply the classifications and run `trace_power_paths()`. Check input, protection, switching, regulation, load branches, filtered rails, split analog/digital rails, and return domains.

Do not merge similarly named split rails without circuit evidence.

### 4. Recommend routing treatment

For each power net, recommend a plane, a wide trace, a normal-width low-demand branch, or manual review.

Base widths on current evidence and board/fabrication rules. When fabrication parameters are unknown, label the recommendation as preliminary.

### 5. Validate coverage

Check that every identified source-to-load path is represented, ground variants are intentionally handled, nets excluded from signal routing are claimed by a later power or plane stage, and split domains are not accidentally joined by broad patterns.

## Output contract

Provide:

1. Input board and analysis scope.
2. A component-classification table with evidence, estimate, source, and confidence.
3. Traced power paths.
4. A power-net table with recommended width or treatment and rationale.
5. Ready-to-use `--power-nets` and `--power-nets-widths` arguments where appropriate.
6. Candidate plane nets and domain warnings.
7. Unverified assumptions and missing information.

Do not run `route.py` or `route_planes.py` unless the user explicitly requests execution.

## Technical reference

Use `.claude/skills/analyze-power-nets/SKILL.md` for project APIs, component-role definitions, and report examples. Treat literal `WebSearch` wording as a generic request to use available web access, not as a Codex tool name.
