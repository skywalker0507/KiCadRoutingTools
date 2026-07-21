---
name: identify-diff-pairs
description: Identify and verify differential pairs in a KiCad PCB from net names, pin metadata, datasheets, and series-component tracing; classify polarity-swap safety; recommend impedance and matching parameters; and generate route_diff.py commands. Do not route unless explicitly asked.
---

# Identify Differential Pairs

Follow `docs/agent-workflows/README.md` and `docs/agent-workflows/diff-pair-analysis.md`.

Use `.claude/skills/identify-diff-pairs/SKILL.md` as a technical reference for interface guidance and project command details. Replace Claude slash-command references with matching Codex skills such as `$recommend-stackup`.

## Inputs

Require an input `.kicad_pcb` path. Accept optional known interfaces, stackup/manufacturer impedance data, matching tolerances, and permission for datasheet lookup.

This skill is analysis-only by default. Do not run `route_diff.py` unless the user explicitly asks to route or execute.

## Procedure

### 1. Establish the name-based baseline

Run:

```bash
python3 -X utf8 list_nets.py <board.kicad_pcb> --diff-pairs
```

Record the result as candidate pairs. Net-name matching alone is not confirmation.

### 2. Inspect local component and pin evidence

Parse the board and inspect likely interface devices:

```python
from kicad_parser import parse_kicad_pcb

pcb = parse_kicad_pcb("<board.kicad_pcb>")
for ref, fp in pcb.footprints.items():
    for pad in fp.pads:
        print(ref, fp.footprint_name, pad.pad_number, pad.pinfunction, pad.net_name)
```

Prioritize components whose value, footprint, or pins suggest USB, Ethernet, LVDS, HDMI/TMDS, DisplayPort, PCIe, SATA, MIPI, SerDes, DDR clocks/strobes, CAN, RS-422/485, PHYs, redrivers, or transceivers.

### 3. Verify missing or generic pin metadata

For each candidate not confirmed locally:

1. Identify the exact component or mark it ambiguous.
2. Find an official manufacturer datasheet, reference manual, or pinout.
3. Map documented differential pins to pad numbers and board nets.
4. Trace through two-pad series resistors, capacitors, inductors, or ferrites to the routed-side nets.
5. Record the source and confidence.

Classify each result:

- `CONFIRMED`: both nets map to a documented differential pin pair.
- `SUSPECTED`: name or topology suggests a pair but documentation is incomplete.
- `FALSE_POSITIVE`: name-based detection is contradicted by pin function or topology.

Never fabricate pin mappings or interface requirements. Mark external facts `UNVERIFIED` when web access is unavailable.

### 4. Recommend parameters

For every confirmed pair, record:

- Interface type.
- Differential impedance target and source.
- Whether intra-pair matching is required and its tolerance when known.
- Whether inter-pair/lane matching is required.
- Preferred reference plane and routing layers.
- AC-coupling and termination constraints.

When the board stackup is missing or generic, follow `$recommend-stackup` before presenting `--impedance` results as manufacturable.

### 5. Classify polarity swapping

Return `polarity_swappable: yes|no|unknown` for every confirmed pair.

- `yes` requires verified endpoint support for polarity inversion or reassignment.
- `no` applies to fixed-function or polarity-critical interfaces and asymmetric attachments.
- Treat `unknown` as `no` in commands.

Never add `--polarity-swap-nets` merely because routing is difficult.

### 6. Generate commands

Group only pairs sharing compatible impedance, gap, layer, and matching requirements.

Generate commands using fresh output paths and captured logs:

```bash
python3 -X utf8 route_diff.py <input.kicad_pcb> <output.kicad_pcb> \
  --nets <patterns...> --impedance <ohms> [matching flags] \
  [--polarity-swap-nets <verified-safe-patterns...>] \
  2>&1 | tee <log-path>
```

For polarity-critical pairs, omit `--polarity-swap-nets`; swaps are denied by default.

## Output

Return:

1. Name-based baseline candidates.
2. Confirmed pairs grouped by interface, including pin/net mapping, evidence, source, and confidence.
3. Suspected pairs and the missing evidence needed to confirm them.
4. False-positive name matches.
5. Per-pair impedance, matching requirements, layer/reference-plane guidance, and `polarity_swappable` verdict.
6. Ready-to-run commands with fresh output paths and logs.
7. Stackup, datasheet, or topology warnings.

When the user explicitly requests execution, preserve the original board, run one compatible group at a time, inspect logs, and verify DRC, connectivity, pair gap, and skew before continuing.
