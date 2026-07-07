# Shared Agent Workflow Conventions

This directory defines platform-neutral execution contracts for AI-assisted PCB analysis and routing.

## Layering

The repository has three related layers:

1. `docs/agent-workflows/` defines shared inputs, modes, safety rules, outputs, and verification requirements.
2. `.agents/skills/` contains Codex-native workflows with explicit steps and tool behavior.
3. `.claude/skills/` contains the existing detailed domain playbooks and the KiCad plugin's Claude-specific behavior.

The Claude skill files remain valuable technical references, but Codex must not blindly inherit Claude-specific tool names, slash-command syntax, GUI assumptions, or plugin result formats.

## Instruction precedence

For a Codex run, apply instructions in this order:

1. The user's explicit request.
2. Repository `AGENTS.md` and any closer directory overrides.
3. The selected `.agents/skills/<name>/SKILL.md`.
4. The corresponding shared workflow in this directory.
5. Relevant technical details from `.claude/skills/<name>/SKILL.md`.

When a Claude skill conflicts with a Codex skill about execution mode, tool use, output format, or whether commands should run, follow the Codex skill.

## Execution modes

Every workflow must determine its mode before running commands.

### Analysis mode

- Read the board and supporting files.
- Run read-only inspection commands when useful.
- Do not create routed or modified PCB files.
- A report or command recommendation is the output.

### Plan-only mode

- Produce an ordered, executable plan with exact input/output paths and commands.
- Inspection commands may run.
- Do not run commands that modify the design or generate routed boards.
- State assumptions and unresolved decisions explicitly.

### Execute mode

- Run the requested workflow.
- Preserve the original board and write every modifying stage to a fresh output path.
- Capture logs for routing and verification steps.
- Inspect results after each major stage and adjust parameters when evidence supports a retry.
- Stop rather than silently continuing when a mandatory stage fails or drops nets.

### Plugin-compatible plan mode

Use this mode only when the user explicitly asks for a plan intended for the existing KiCad plugin Claude tab or its GUI result parser.

- Follow the plugin-specific output contract in the matching `.claude/skills/` file.
- Assume the plugin may execute each generated step only once.
- Pre-compute conservative, fabrication-valid parameters because the plugin plan may not perform iterative retries.

Normal VS Code, Codex CLI, and Codex app requests must not default to plugin-compatible mode.

## Board safety

- Treat `.kicad_pcb`, `.kicad_sch`, and `.kicad_pro` as user design data.
- Do not edit the original board in place unless the user explicitly requests it.
- Before a modifying command, state the input path and intended output path.
- Use stable stage names such as `board_step1_fanout.kicad_pcb` and avoid overwriting earlier evidence.
- Route A/B comparisons to different output names; sibling `.kicad_pro` files can affect later runs.
- Do not commit generated boards, logs, downloaded datasheets, or stress-test corpora.

## Tool vocabulary

Write workflows in capability terms instead of model-specific tool names:

- “Search the web” means use available browser/web access.
- “Read the file” means use the available repository/file tools.
- “Run the command” means use the workspace shell.
- “Search the repository” means use text or semantic repository search.

A literal Claude tool name such as `WebSearch`, `Bash`, `Read`, `Grep`, or `Glob` in a technical reference describes an operation, not an API that Codex must call by that name.

## External facts

- Prefer primary sources such as manufacturer datasheets, reference manuals, interface standards, and fabrication capability pages.
- Record the part number, source, relevant value, and confidence.
- Never fabricate current ratings, pin functions, rise times, impedance targets, or fabrication limits.
- If network access is unavailable, mark external conclusions as unverified and continue only with local evidence.

## Verification

- DRC and electrical connectivity are separate requirements.
- Use the clearance actually used by the route or defined by the board/net class.
- Do not claim success from the router's own routed tally alone.
- Preserve and report the exact commands used for reproducibility.
- A final report must distinguish PASS, FAIL, WARN, NOT RUN, and UNKNOWN.
