---
name: analyze-power-nets
description: Identify power and ground nets in a KiCad PCB, trace supply paths, verify component roles and ratings, recommend trace widths or planes, and generate power-routing arguments. Use when power-net metadata is missing or uncertain; do not automatically route the board.
---

# Analyze Power Nets

Follow `docs/agent-workflows/README.md` and `docs/agent-workflows/power-net-analysis.md`.

Use `.claude/skills/analyze-power-nets/SKILL.md` as a technical reference for project APIs, component-role definitions, and report examples. Translate literal Claude tool names such as `WebSearch` into the equivalent available Codex capability.

## Inputs

Require an input `.kicad_pcb` path. Accept optional known supply voltages, source limits, expected loads, fabrication rules, copper weight, and manufacturer information.

This skill is analysis-only by default. Do not run `route.py` or `route_planes.py` unless the user explicitly asks to execute power routing.

## Procedure

### 1. Extract board evidence

Use the project's power analysis APIs:

```python
from analyze_power_paths import (
    analyze_pcb,
    get_components_needing_analysis,
    classify_component,
    trace_power_paths,
    get_power_net_recommendations,
    format_analysis_report,
    ComponentRole,
)

components, pcb_data = analyze_pcb("<board.kicad_pcb>")
unknown = get_components_needing_analysis(components)
```

Also inspect:

- Component value, footprint, reference, and pad connectivity.
- Pin functions and power pin metadata.
- Existing net classes and widths.
- Existing zones or plane layers.
- Split ground and supply domains.

### 2. Apply deterministic classifications carefully

Use local automatic classification for obvious passive roles such as decoupling capacitors, series inductors/ferrites, fuses, and LEDs.

Do not classify an IC, connector, diode, transistor, or regulator solely from its reference prefix. Check the actual part, pins, and topology.

### 3. Verify unknown components

For each important unknown component:

1. Identify the exact part number or mark it ambiguous.
2. Search for a primary source, preferably the manufacturer datasheet or reference manual.
3. Record the relevant evidence: supply pins, output rating, supply demand, connector rating, switch topology, or protection topology.
4. Classify it as `POWER_SOURCE`, `CURRENT_SINK`, `PASS_THROUGH`, or `SHUNT`.
5. Record the estimated demand/rating and confidence: `verified`, `estimated`, or `unknown`.
6. Apply the classification through `classify_component()`.

Never fabricate ratings. If network access is unavailable, use local evidence and mark external values `UNVERIFIED`.

### 4. Trace supply paths

After classification:

```python
paths = trace_power_paths(pcb_data, components)
recommendations = get_power_net_recommendations(pcb_data, components, paths)
```

Check:

- Input through protection, switching, and regulation.
- Regulator outputs and downstream loads.
- Filtered and split analog/digital rails.
- Ground-domain boundaries.
- Nets upstream of known power rails.

Do not merge similarly named split rails without circuit evidence.

### 5. Recommend treatment

For every identified power net, choose one:

- Plane or zone.
- Wide trace.
- Normal-width low-demand branch.
- Manual review.

Base width recommendations on verified or clearly labeled estimated demand plus board/fabrication rules. When copper weight, thermal target, or fabrication limits are unknown, label the width preliminary.

Ground nets are power nets, but distinguish GND, AGND, GNDA, PGND, VSS, and other domains instead of collapsing them blindly.

### 6. Reconcile routing coverage

Verify that:

- Every identified source-to-load path appears in the report.
- Nets excluded from signal routing are claimed by a power or plane stage.
- Split domains are not joined by broad patterns.
- Candidate plane nets and wide-trace nets do not conflict.

## Output

Return:

1. Board path and scope.
2. Component classification table with role, evidence, rating/demand, source, and confidence.
3. Traced supply paths.
4. Power-net table with estimated demand, recommended width/treatment, and rationale.
5. Ready-to-use `--power-nets` and `--power-nets-widths` arguments where appropriate.
6. Candidate plane nets and split-domain warnings.
7. Unverified assumptions and missing information.

When the user explicitly requests execution, preserve the original board, state fresh input/output paths, capture logs, and verify the result with DRC and connectivity checks.
