# Repository Instructions for Codex

These instructions apply to the whole repository.

## Canonical engineering guidance

Read `CLAUDE.md` before making code changes. Despite its filename, it contains the project's detailed cross-agent engineering guidance for Python execution, Rust builds, routing verification, CLI/GUI parity, parser behavior, and PCB data structures.

For Codex workflow behavior, `.agents/skills/` and this file take precedence over Claude-specific instructions. Otherwise, follow both.

## Repository architecture

- The main routing implementation is Python, with a Rust accelerator under `rust_router/`.
- Prefer Python-only changes unless a Rust change is clearly necessary.
- Build the Rust router with `python3 build_router.py`; do not run `cargo build` directly.
- The CLI entry points and KiCad GUI plugin call the same routing engine but have separate argument/UI plumbing. Keep CLI and GUI behavior, defaults, documentation, and persistence settings in sync.
- Treat `.kicad_pcb`, `.kicad_sch`, and `.kicad_pro` as user design data. Preserve the original input unless the user explicitly requests an in-place edit.

## Working conventions

- Use `python3`. On Windows, fall back to `py -3` or `python` only when `python3` is unavailable.
- Add `-X utf8` when command output may contain characters such as `Ω`.
- Inspect the relevant implementation, tests, and documentation before editing.
- Prefer focused changes over broad refactors.
- Do not commit generated boards, stress-test corpora, temporary logs, build outputs, downloaded datasheets, or local environment files.
- Update user-facing documentation when commands, options, defaults, or behavior change.
- Surface the cost of a Rust change before making it. Rust changes require a crate version bump, documentation updates, rebuilding, and redistribution of platform binaries.

## Verification requirements

- Run the narrowest relevant tests first, then broader tests when a change affects shared routing behavior.
- DRC and electrical connectivity are separate requirements. Run both `check_drc.py` and `check_connected.py` before declaring a routed board clean.
- Use the actual routing clearance or board/net-class rules when grading DRC. Do not invent a stricter clearance.
- Route A/B comparisons to fresh output paths because a sibling output `.kicad_pro` can affect later runs.
- Do not compare complete generated PCB files or hashes to test determinism; generated UUIDs vary. Compare routed counts, DRC results, connectivity, and other semantic outputs.
- When changing a shared engine parameter or default, check the CLI parser, GUI call sites, controls, config dictionaries, and `settings_persistence.py`.

## Agent workflow layers

- `docs/agent-workflows/` contains platform-neutral inputs, modes, safety rules, output contracts, and verification requirements.
- `.agents/skills/` contains Codex-native workflows. These are authoritative for Codex execution behavior.
- `.claude/skills/` contains detailed domain playbooks and Claude-specific behavior. Use them as technical references, not as Codex execution contracts.

Apply this precedence for a Codex skill run:

1. The user's explicit request.
2. `AGENTS.md` and any closer directory override.
3. The selected `.agents/skills/<name>/SKILL.md`.
4. `docs/agent-workflows/`.
5. Relevant technical details from `.claude/skills/<name>/SKILL.md`.

Ignore Claude-specific tool names, slash-command syntax, GUI assumptions, and result formats when they conflict with the Codex skill.

## Codex skills

Use `/skills` or mention a skill explicitly with `$skill-name`:

- `$plan-pcb-routing`
- `$analyze-power-nets`
- `$find-high-speed-nets`
- `$identify-diff-pairs`
- `$recommend-plane-mappings`
- `$recommend-stackup`
- `$diagnose-routing-failures`
- `$review-routed-board`
- `$stress-test-router`

When a skill references another workflow, follow the matching `$skill-name`; do not treat Claude-style `/skill-name` text as a Codex slash command.

## Workflow modes

- Analysis mode is read-only and produces findings or recommendations.
- Plan-only mode may run inspection commands but must not generate routed boards.
- Execute mode is used only when the user explicitly asks to run, route, modify, or produce an output board. It uses fresh staged output paths and verifies every major stage.
- Plugin-compatible plan mode is used only when the user explicitly asks for output intended for the KiCad plugin's machine-readable plan parser.

Never assume a request to “analyze” or “plan” authorizes board modification.

## Plugin AI providers

- `kicad_routing_plugin/ai_providers.py` owns executable discovery, command construction, model/effort choices, skill syntax, JSONL event parsing, final-result extraction, and authentication guidance.
- The plugin currently supports `ClaudeProvider` and `CodexProvider` behind one provider-neutral runner.
- Plugin-driven provider runs are read-only; they analyze a temporary board snapshot and return a report or plan. The plugin's local routing engines make actual PCB changes only after user review.
- Codex plugin runs use `codex exec --json --sandbox read-only --search` and the user's existing Codex CLI authentication/configuration.
- Keep compatibility imports and saved settings working when renaming legacy Claude-specific classes or files.
- Provider tests must not import wxPython; keep provider parsing and command construction in the pure-Python provider module.
- Do not display raw reasoning/chain-of-thought from provider event streams. Show only safe activity summaries and final messages.

## External evidence

- Prefer primary sources such as official component datasheets, reference manuals, interface standards, and manufacturer capability pages.
- Never fabricate pin functions, current ratings, rise times, impedance targets, or fabrication limits.
- When network access is unavailable, distinguish local evidence from unverified external assumptions.

## Board modification safety

- State the input and intended output paths before a modifying command.
- Preserve the original board by default.
- Capture logs for routing and verification stages.
- Do not continue past unexplained dropped nets, failed fanout summaries, or mandatory verification failures.
- Do not retry blindly; change parameters only when logs, geometry, stackup, or fabrication rules justify the change.

## Scope of the current integration

Codex is supported both as a repository agent and as a selectable KiCad plugin AI provider. The plugin provider is intentionally based on non-interactive `codex exec --json`; a future App Server integration may add persistent threads, richer approvals, and history without replacing the provider interface.
