---
name: diagnose-routing-failures
description: Diagnose failed KiCad routes from router logs and board geometry, parse structured summaries and failure histories, identify blockers and spatial patterns, classify the root cause, and produce one targeted retry command. Do not execute the retry unless explicitly asked.
---

# Diagnose Routing Failures

Follow `docs/agent-workflows/README.md` and `docs/agent-workflows/failure-diagnosis.md`.

Use `.claude/skills/diagnose-routing-failures/SKILL.md` as a technical reference for log fields, common failure signatures, and command examples.

## Inputs

Require:

- The board used as input to the failed stage, or the latest routed board containing successful routes.
- One or more routing log paths.

Accept optional original commands, fabrication limits, intended net group, and prior retry logs.

Diagnosis is read-only by default. Do not run a retry unless the user explicitly asks to execute it.

## Procedure

### 1. Parse structured results

Extract every `JSON_SUMMARY` from the logs and record relevant fields, including:

- Failed single-ended nets.
- Failed multipoint nets and unconnected pad coordinates.
- Connected/total multipoint pad counts.
- Failed differential pairs.
- Fanout requested/escaped/failed counts and unescaped nets.
- Plane-repair blocker nets.

Prefer structured final-board connectivity fields over informal routed tallies.

### 2. Read failure histories

Extract failed-net histories and record:

- Route attempts.
- `ripped_by` relationships and escalation level.
- Whether ripped nets were restored.
- Repeated mutual ripping.
- Search-budget or no-path outcomes.

A net ripped and never restored implicates both the failed net and the route that displaced it.

### 3. Read blocking evidence

Search logs for blocked-frontier, no-rippable-blocker, route-stuck, dropped-fanout, and retry-failure messages.

Record blocker net names, coordinates, layers, and the exact log evidence. Do not infer blockers only from visual proximity.

### 4. Correlate with board geometry

Parse the board and map each failed net's pads, layers, nearby footprints, BGA/PGA regions, board-edge constraints, keepouts, and congested corridors.

State the spatial pattern explicitly, for example:

- Failures cluster around one package side.
- All failures must cross one corridor.
- Failures are isolated to one layer.
- Endpoints have conflicting launch layers.
- Fanout dropped the same nets before signal routing.

### 5. Classify the root cause

Evaluate targeted causes before broad parameter changes:

- Dropped or incomplete fanout.
- BGA/PGA exclusion-zone blockage.
- Keepout or board-edge blockage.
- Corridor congestion.
- Same-layer crossing conflict.
- Coarse grid or geometry incompatible with pad pitch.
- Search/retry budget exhaustion.
- Plane-repair rip-up not restored.
- Genuine routing-capacity or placement problem.
- Geometry below fabrication limits.

Return a primary diagnosis, confidence, and plausible competing explanations.

### 6. Build one targeted retry

Generate one command that routes only the failed or unrestored nets from the latest board containing the successful routes.

Use:

- A fresh output board.
- A fresh log path.
- The original successful routing parameters unless evidence justifies a change.
- The same power-width parameters when a failed net is a power net.
- Full copper-layer lists where multilayer defaults would strand routes.

Explain every changed flag in one line with supporting evidence.

Do not immediately propose global clearance/width reduction. Escalate only after targeted causes are excluded, and never below verified fabrication floors.

### 7. Define verification and stop conditions

Require the retry to be checked with:

- `check_connected.py` for the affected nets or whole board.
- `check_drc.py` at the actual routed floor.
- Any relevant fanout, pair, or plane check.

If the retry fails, diagnose the new log because the dominant failure mode may have changed. Do not repeat the same command without new evidence.

## Output

Return:

1. Board and log paths.
2. Structured failure summary.
3. Failed-net history and blocker summary.
4. Spatial correlation by component, region, and layer.
5. Primary diagnosis, confidence, and alternatives.
6. One targeted retry command with fresh output/log paths.
7. Parameter-change rationale.
8. Verification commands and stop conditions.

When the user explicitly asks to execute the retry, preserve the original board, run the command, inspect the new structured output, and report the verification result rather than assuming the retry worked.
