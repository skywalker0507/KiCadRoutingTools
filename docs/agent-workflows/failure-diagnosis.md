# Routing Failure Diagnosis Workflow

## Purpose

Root-cause failed routes from a board and routing logs, correlate structured failures with board geometry, classify the most likely failure mode, and produce a targeted retry command.

## Inputs

Required:

- The board used as input for the failed routing stage, or the latest routed output containing successful routes.
- One or more routing log files.

Optional: original command, fabrication limits, intended net group, and prior retry logs.

Diagnosis is read-only by default. Do not execute a retry unless the user explicitly asks.

## Procedure

1. Parse every `JSON_SUMMARY` and record failed single-ended nets, failed multipoint nets, connected/total pad counts, dropped fanout nets, and other structured fields.
2. Read failed-net histories and identify which routes ripped other nets, escalation levels, and whether ripped nets were restored.
3. Extract blocking reports, stuck coordinates, layers, and named blockers.
4. Parse the board and map failed-net endpoints, nearby components, BGA/PGA exclusion regions, congested corridors, and layer usage.
5. State the spatial pattern explicitly. Do not recommend global parameter changes before checking targeted causes.
6. Classify the failure using evidence, for example exclusion-zone blockage, dropped fanout, corridor congestion, layer conflict, grid/pitch mismatch, exhausted search budget, or genuine board capacity.
7. Produce one targeted retry command that routes only the failed nets from the latest board containing successful routes. Use a fresh output path and log path.
8. Explain every changed parameter and the evidence supporting it.
9. Require connectivity and relevant DRC checks after the retry.

Do not retry blindly. When the failure is caused by placement, insufficient layers, or geometry below fabrication limits, report infeasibility instead of repeatedly lowering constraints.

## Output contract

Provide:

1. Input board and log paths.
2. Structured failure summary.
3. Failed-net history and blocker summary.
4. Spatial correlation by component, region, and layer.
5. Primary diagnosis, confidence, and competing explanations.
6. One targeted retry command with fresh output/log paths.
7. Parameter-change rationale.
8. Verification commands and stop conditions.

## Technical reference

Use `.claude/skills/diagnose-routing-failures/SKILL.md` for project log fields, common failure signatures, and command examples.
