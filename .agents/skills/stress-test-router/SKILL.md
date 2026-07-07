---
name: stress-test-router
description: Explicitly run reproducible router stress tests on a real-world KiCad board corpus, collect completion/DRC/connectivity/resource results, aggregate regressions, and prepare deduplicated GitHub issue drafts. Expensive workflow; never invoke implicitly.
---

# Stress Test Router

Follow `docs/agent-workflows/README.md` and `docs/agent-workflows/stress-testing.md`.

Use `.claude/skills/stress-test-router/SKILL.md` and `tests/stress/RUNBOOK.md` as technical references for corpus preparation, result schema, operational limits, aggregation, and known findings.

This workflow is expensive. Use it only when the user explicitly requests stress testing, corpus testing, or regression testing.

## Inputs

Require:

- `$STRESS_DIR` outside the repository.
- Board set or explicit board list.
- Mode: `single-board`, `small-batch`, or `existing-harness`.

Accept optional comparison revision, result-set name, concurrency, resource limits, and issue-reporting scope.

## Important mode distinction

The current `tests/stress/run_queue.sh` and `run_board.sh` queue path launches headless Claude workers. Running it validates the existing Claude-based harness; it does not make Codex the worker.

- `single-board`: Codex directly follows `tests/stress/RUNBOOK.md` for one board.
- `small-batch`: Codex directly processes an explicit, bounded board list and writes the expected result files.
- `existing-harness`: run the current queue scripts only when the user explicitly asks to test the Claude-based harness.

Never silently launch `claude -p` from Codex-native mode.

## Procedure

### 1. Protect the repository

- Keep downloaded, normalized, stripped, routed, logged, and result artifacts under `$STRESS_DIR`.
- Never commit corpus files or generated boards.
- Do not modify the tools repository during board runs.

### 2. Prepare or validate the corpus

If validated unrouted boards already exist, reuse them. Otherwise use the preparation scripts under `tests/stress/`, the KiCad-bundled Python where `pcbnew` is required, and `validate_boards.py` before routing.

Record corpus source revisions and preparation failures.

### 3. Read the runbook

Read `tests/stress/RUNBOOK.md` in full before starting a board. Follow its result schema, stage requirements, and stop conditions.

### 4. Apply resource guards

- Route one board per isolated run directory.
- Use the repository's limited runner for heavy commands where the runbook requires it.
- Respect per-step memory limits and bounded concurrency.
- Treat crashes, hangs, and resource-limit kills as findings, not noise.
- Never leave a routing process running after ending the task.

### 5. Route and verify each board

For every board:

1. Analyze it using `$plan-pcb-routing` in execute mode.
2. Pass all copper layers to fanout and differential routing on multilayer boards.
3. Inspect fanout `JSON_SUMMARY`; do not continue with unexplained dropped balls.
4. Capture exact commands, stage outputs, logs, and parameter decisions.
5. Run DRC, connectivity, orphan-stub, and applicable pair/plane checks.
6. Write the expected results JSON and concise finding narrative.

### 6. Aggregate

Produce a summary including:

- Board and layer count.
- Routable nets and completion percentage.
- Multipoint pads connected/total.
- DRC baseline, final, and delta.
- Connectivity verdict.
- Orphan stubs.
- Wall time and resource failures.
- Distinct issue candidates.

Flag completion below 100%, positive DRC delta, connectivity failures, crashes, hangs, and resource-limit kills.

### 7. Deduplicate findings

Search existing issues before drafting action:

- Open issue with same root cause: propose adding new evidence.
- Closed issue with a true recurrence: propose reopening with evidence.
- Adjacent but distinct bug: draft a new issue and explain the distinction.
- No match: draft a new issue.

Do not create, reopen, label, or comment on issues without explicit user approval after presenting all drafts.

## Output

Return:

1. Corpus, revision, mode, board set, and resource-limit summary.
2. Board result table sorted by completion or severity.
3. Crashes, hangs, resource failures, and correctness regressions.
4. Deduplicated findings with reproduction commands and log evidence.
5. Existing issue matches and proposed action.
6. Issue drafts awaiting approval, or links to actions the user approved.
7. Corpus preparation problems and untested boards.

Keep detailed per-board evidence in result files rather than flooding the final response.
