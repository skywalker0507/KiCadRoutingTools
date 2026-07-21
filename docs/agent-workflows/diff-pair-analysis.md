# Differential Pair Analysis Workflow

## Purpose

Identify confirmed and suspected differential pairs, verify them against component pin functions and primary documentation, classify polarity-swapping safety, and recommend routing parameters and commands.

## Inputs

Required:

- Input `.kicad_pcb` path.

Optional:

- Known interfaces and expected impedance targets.
- Stackup or manufacturer impedance table.
- Matching tolerances.
- Permission to use network access for datasheet verification.

This workflow is analysis-only unless the user explicitly asks to route differential pairs.

## Procedure

### 1. Establish a name-based baseline

Run:

```bash
python3 -X utf8 list_nets.py <board.kicad_pcb> --diff-pairs
```

Record these as candidates, not automatically confirmed pairs.

### 2. Inspect local pin metadata

Parse the board and inspect `pinfunction`, pad number, net name, component value, and footprint for likely high-speed interface devices.

Look for documented pairs such as P/N, +/- and interface-specific TX/RX, clock, strobe, or lane naming.

### 3. Verify against primary documentation

When local pin metadata is missing or generic:

1. Identify the exact component.
2. Find the official datasheet, reference manual, or pinout.
3. Map documented differential pins to pad numbers and board nets.
4. Trace through two-pad series resistors, capacitors, inductors, or ferrites to the routed-side nets.
5. Record the source and confidence.

A pair is `CONFIRMED` only when both nets map to a documented differential pin pair. A name-only or topology-only candidate is `SUSPECTED`.

### 4. Classify interface requirements

For every confirmed pair, record:

- Interface type.
- Differential impedance target.
- Whether intra-pair matching is required and the tolerance when known.
- Whether inter-pair or lane matching is required.
- Preferred reference plane and layers.
- Any AC-coupling or termination constraints.

Use the stackup workflow before relying on `--impedance` when the board stackup is missing or unrealistic.

### 5. Classify polarity swapping

Return `yes`, `no`, or `unknown` for every pair.

- `yes` requires explicit endpoint capability to compensate for a P/N swap.
- `no` applies to polarity-critical fixed-function interfaces or asymmetric attachments.
- Treat `unknown` as `no` for routing commands.

Never add `--polarity-swap-nets` based only on the fact that two traces are difficult to route.

### 6. Generate commands

Group pairs only when they share compatible routing parameters. Generate commands with fresh output paths and captured logs.

Example shape:

```bash
python3 -X utf8 route_diff.py <input.kicad_pcb> <output.kicad_pcb> \
  --nets <patterns...> --impedance <ohms> [matching flags] \
  [--polarity-swap-nets <verified-safe-patterns...>] \
  2>&1 | tee <log-path>
```

Do not run the commands unless the user explicitly requests execution.

## Output contract

Provide:

1. Name-based baseline candidates.
2. Confirmed pairs grouped by interface, with evidence and source.
3. Suspected pairs and the missing evidence needed to confirm them.
4. False-positive name matches.
5. Per-pair parameters and `polarity_swappable: yes|no|unknown`.
6. Ready-to-run commands using fresh output files.
7. Stackup or documentation warnings.

## Technical reference

Use `.claude/skills/identify-diff-pairs/SKILL.md` for project command details and interface guidance. Replace Claude slash-command references with the matching Codex skill, such as `$recommend-stackup`.
