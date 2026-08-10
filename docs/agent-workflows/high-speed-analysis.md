# High-Speed Net Analysis Workflow

## Purpose

Identify high-speed, RF, and controlled-impedance nets; verify interface speeds and pin mappings; propagate classifications through series components; and recommend impedance routing and GND return-path parameters.

## Inputs

Required: an input `.kicad_pcb` path.

Optional: known interfaces, stackup, fabrication limits, impedance table, and permission to use network access for datasheet verification.

This workflow is analysis-only unless the user explicitly asks to route identified nets.

## Procedure

1. Parse the board and run `list_nets.py --diff-pairs --power` for context.
2. Use net-name patterns and component keywords only as candidate generation. Do not treat a name such as `CLK`, `USB`, or `RF` as verified speed or impedance evidence.
3. Inspect component values, footprints, pad pin functions, and endpoints.
4. For each material interface, prefer official manufacturer documentation and record interface type, maximum clock or data rate, output rise/fall time when specified, I/O standard, relevant pins, source, and confidence.
5. Map interface pins to board nets. Propagate the classification through two-pad series resistors, capacitors, inductors, and ferrites.
6. Scan broadly for RF/antenna candidates, but confirm that the net connects an RF port to an antenna termination or matching network. Reject coincidental keyword matches and ground-shell nets.
7. Separate single-ended controlled-impedance nets from differential pairs. Differential pairs belong in the differential-pair workflow.
8. Require a credible stackup before presenting router-computed impedance widths as manufacturable.
9. Recommend a GND return-via distance based on verified signal edge/speed requirements and physical spacing limits. State when the value is a heuristic rather than a design requirement.

## Output contract

Provide:

1. Initial name/component candidates and which were rejected.
2. Interface groups with component endpoints, nets, verified speed/rise-time data, source, and confidence.
3. Nets added by propagation through series components.
4. Confirmed RF/antenna feeds with endpoint and impedance evidence.
5. Single-ended controlled-impedance nets and differential-pair groups separately.
6. Recommended target impedance, routing stage, layers/reference plane, and GND return-via distance.
7. Ready-to-run command examples with fresh output paths, but do not execute them unless explicitly requested.
8. Stackup, fabrication, and documentation warnings.

Never fabricate speed, rise-time, or impedance values. A datasheet-confirmed result overrides a name-pattern guess.

## Technical reference

Use `.claude/skills/find-high-speed-nets/SKILL.md` for project heuristics, RF candidate logic, series-passive propagation, speed tiers, and command details. Translate Claude-specific tool and slash-command wording to Codex-native behavior.
