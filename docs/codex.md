# Codex Integration

KiCadRoutingTools supports OpenAI Codex in two places:

1. Repository-level workflows for the Codex IDE extension, Codex CLI, and Codex app.
2. A selectable **OpenAI Codex** provider inside the KiCad plugin's AI tab and field-level AI dialogs.

The plugin keeps Claude Code support and uses one provider-neutral runner for both CLIs.

## Repository workflow architecture

- `AGENTS.md` — repository-wide engineering, verification, and board-safety instructions.
- `.agents/skills/` — Codex-native workflows with explicit inputs, modes, outputs, and stop conditions.
- `docs/agent-workflows/` — platform-neutral workflow contracts.
- `.claude/skills/` — detailed project playbooks and Claude-specific plugin references.

Codex skills decide execution mode, tool behavior, safety, and output format. Claude playbooks remain technical references rather than Codex execution contracts.

## Install and authenticate Codex CLI

Install a current Codex CLI and authenticate it in a terminal:

```bash
codex login
```

Confirm that the CLI is visible to desktop applications:

```bash
codex --version
```

KiCad launched from a desktop icon may not inherit the shell PATH. The plugin therefore also checks common locations such as:

```text
~/.local/bin/codex
/opt/homebrew/bin/codex
/usr/local/bin/codex
%APPDATA%/npm/codex.cmd
```

Restart KiCad after installing or moving the CLI.

## Use Codex inside the KiCad plugin

Open **KiCad Routing Tools → AI** and choose:

```text
Provider: OpenAI Codex
```

The tab exposes:

- Provider selection: Claude Code or OpenAI Codex.
- Model: Default uses the CLI configuration; a custom model ID may be entered.
- Effort: Default, minimal, low, medium, high, or xhigh for Codex.
- Plan Routing.
- Review Routed Board.
- Diagnose Routing Failures.
- Execution of selected plan steps through the plugin's local routing engines.

The selected provider, model, effort, transcript, and loaded plan are persisted with the existing dialog settings. Older Claude-only settings remain compatible.

Buttons historically labeled **Ask Claude** on the Differential and Planes tabs are renamed to **Ask AI** at runtime and use the provider selected on the AI tab.

## Plugin provider architecture

The provider layer lives in:

```text
kicad_routing_plugin/ai_providers.py
```

Each provider owns:

- executable discovery;
- model and effort choices;
- skill invocation syntax;
- CLI command construction;
- JSONL event parsing;
- final-result extraction;
- authentication guidance.

The GUI runner and provider selector remain in:

```text
kicad_routing_plugin/claude_gui.py
```

The historical filename and class names are retained to avoid breaking imports and saved settings. New aliases such as `AITab`, `AISkillDialog`, and `AISkillRunner` are also exported.

### Claude provider

Claude keeps the existing command contract:

```bash
claude -p <prompt> \
  --output-format stream-json --verbose \
  --allowedTools Read,Glob,Grep,Bash,WebSearch
```

### Codex provider

Codex uses non-interactive JSONL execution:

```bash
codex exec --json \
  --sandbox read-only \
  [--model <model>] \
  [--config 'model_reasoning_effort="high"'] \
  <prompt>
```

Plugin AI runs are deliberately read-only. Codex analyzes the temporary board snapshot and emits a plan or report; actual PCB modification is performed later by the plugin's existing routing engines after the user reviews and selects steps.

Claude-style skill prompts such as `/identify-diff-pairs` are converted only for known skills to Codex syntax such as `$identify-diff-pairs`. Filesystem paths such as `/tmp/router.log` are left unchanged.

The Codex event parser displays agent messages, command/web activity, result status, and token usage where available. It does not expose reasoning text.

## Plugin-compatible plan mode

The Plan Routing button asks either provider for the same machine-readable `RESULT=<JSON>` plan consumed by `claude_plan.py`.

For Codex the prompt explicitly invokes:

```text
$plan-pcb-routing ... plugin-compatible plan mode
```

The provider only plans. The GUI then:

1. validates the JSON steps;
2. fills the native Fanout, Differential, Basic, and Planes controls;
3. lets the user edit or uncheck steps;
4. executes selected steps locally through `PlanExecutor`.

## Repository workflow modes

Codex repository skills distinguish:

- **Analysis** — inspect and report; no routed board is generated.
- **Plan-only** — produce exact staged commands without modifying the board.
- **Execute** — route to fresh staged outputs and verify every major stage.
- **Plugin-compatible plan** — emit the GUI plan schema without executing routes.

A request to analyze or plan does not authorize board modification.

## Available Codex skills

| Skill | Purpose |
|---|---|
| `$plan-pcb-routing` | Plan or execute a complete staged routing workflow. |
| `$analyze-power-nets` | Trace supply paths and recommend power widths or planes. |
| `$find-high-speed-nets` | Verify high-speed, RF, and controlled-impedance nets. |
| `$identify-diff-pairs` | Confirm differential pairs and polarity-swap safety. |
| `$recommend-plane-mappings` | Assign exact plane nets to copper layers for the plugin. |
| `$recommend-stackup` | Review stackup and impedance geometry. |
| `$diagnose-routing-failures` | Root-cause failures and produce a targeted retry. |
| `$review-routed-board` | Run read-only post-route QA and sign-off. |
| `$stress-test-router` | Explicitly run corpus regression tests and prepare issue drafts. |

## Validation

Run the provider unit tests:

```bash
python3 -m unittest tests.test_ai_providers
```

Validate skill structure:

```bash
python3 tests/check_codex_skills.py
```

Then start a fresh Codex session from the repository root and confirm skills with `/skills`.

For a plugin smoke test:

1. Run `codex login`.
2. Open a saved KiCad board.
3. Open KiCad Routing Tools and select **AI → OpenAI Codex**.
4. Run **Review Routed Board** first; it is read-only and should produce a `RESULT=PASS` or `RESULT=FAIL` line.
5. Run **Plan Routing** and confirm the returned steps populate the plugin tabs without modifying the board.

## Board safety

- The live pcbnew board is saved to a temporary analysis snapshot.
- Provider processes run from the repository root so skills are discoverable.
- Codex uses the read-only sandbox.
- Original board files are not modified by AI planning or review.
- DRC and electrical connectivity remain separate pass criteria.
- Actual routing begins only after the user selects and runs plan steps in the GUI.

## Stress-test distinction

The existing `tests/stress/run_queue.sh` harness starts headless Claude workers. Codex-native stress testing therefore uses explicit `single-board` or `small-batch` modes. The `existing-harness` mode is only for intentionally testing the Claude queue, and `$stress-test-router` cannot be invoked implicitly.
