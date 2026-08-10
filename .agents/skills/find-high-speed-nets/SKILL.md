---
name: find-high-speed-nets
description: Identify and verify high-speed, RF, and controlled-impedance nets in a KiCad PCB; map interfaces to pins and nets; trace through series components; and recommend impedance routing and GND return-via parameters. Do not route unless explicitly asked.
---

# Find High-Speed Nets

Follow `docs/agent-workflows/README.md` and `docs/agent-workflows/high-speed-analysis.md`.

Use `.claude/skills/find-high-speed-nets/SKILL.md` as a technical reference for project heuristics, RF candidate logic, series-passive propagation, speed tiers, and command details. Do not inherit Claude tool names or slash-command syntax literally.

## Inputs

Require an input `.kicad_pcb` path. Accept optional known interfaces, stackup, fabrication limits, impedance table, and permission for datasheet lookup.

This skill is analysis-only by default. Do not run routing commands unless the user explicitly asks to execute.

## Procedure

### 1. Establish local context

Parse the board and run:

```bash
python3 -X utf8 list_nets.py <board.kicad_pcb> --diff-pairs --power
```

Report board/net/component counts, candidate differential pairs, and power nets that must be excluded from signal classifications.

### 2. Generate candidates

Use net-name patterns, component values, footprints, pin functions, and high pin counts to generate candidate interfaces and speed tiers.

Treat these only as hypotheses. A name such as `CLK`, `USB`, `RF`, or `DDR` does not by itself establish speed, edge rate, or impedance.

### 3. Verify interface evidence

For each material IC, connector, PHY, memory, transceiver, or RF component:

1. Identify the exact component or mark it ambiguous.
2. Prefer an official manufacturer datasheet or reference manual.
3. Record interface type, maximum clock/data rate, rise/fall time when specified, I/O standard, relevant pins, source, and confidence.
4. Map documented pins to board nets using pad numbers and `pinfunction` metadata.
5. Let verified documentation override name-based estimates.

Never fabricate frequency, rise time, or impedance values. When network access is unavailable, mark external conclusions `UNVERIFIED`.

### 4. Trace through series components

Build connectivity through two-pad resistors, capacitors, inductors, and ferrites. Propagate a verified classification to the routed-side net and report the component path that caused the propagation.

Do not propagate across shunt components or unrelated multi-pad devices.

### 5. Confirm RF and antenna feeds

Use broad candidate detection, then confirm each candidate:

- The source endpoint must be a documented RF/antenna port or balanced RF output.
- The destination must be an antenna termination, connector, module antenna pin, or matching network leading to one.
- Reject ground-shell nets, power rails, large shared nets, and coincidental keyword matches.
- Record whether the port is single-ended or balanced and the documented target impedance.

If an RF source or antenna termination exists but no plausible feed is found, report it as a manual-review warning.

### 6. Separate routing categories

Return separate groups for:

- Single-ended controlled-impedance nets, such as verified RF feeds or SSTL nets.
- Differential impedance pairs, handled by `$identify-diff-pairs` and `route_diff.py`.
- Fast but non-impedance-controlled single-ended nets.
- Low-speed nets requiring no special treatment.

Require a credible stackup before treating router-computed `--impedance` widths as manufacturable. Follow `$recommend-stackup` when necessary.

### 7. Recommend return paths

Recommend GND return-via distance for single-ended signal vias based on verified edge/speed requirements, board density, via size, and clearance.

- State whether the value comes from a documented requirement or a project heuristic.
- Respect the minimum physical spacing.
- Do not apply this recommendation to differential-pair vias when `route_diff.py` handles their return vias separately.

### 8. Generate commands

Provide fresh-path command examples for each controlled-impedance group. Place constrained impedance routing before the general signal route and ensure later broad net patterns exclude those nets.

Do not execute commands unless explicitly requested.

## Output

Return:

1. Initial candidates and rejected false positives.
2. Interface groups with endpoints, nets, verified speed/rise-time data, source, and confidence.
3. Nets propagated through series components.
4. Confirmed RF feeds and target impedance.
5. Separate single-ended impedance, differential impedance, and ordinary fast-net groups.
6. Recommended routing stage, target impedance, layers/reference plane, and GND return-via distance.
7. Ready-to-run commands with fresh output and log paths.
8. Stackup, fabrication, and documentation warnings.

When execution is explicitly requested, preserve the original board, route constrained groups separately, capture logs, and verify DRC, connectivity, and intended impedance/matching constraints before continuing.
