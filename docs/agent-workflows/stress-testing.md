# Router Stress-Test Workflow

## Purpose

Run reproducible routing experiments across a real-world KiCad board corpus, aggregate completion and correctness results, and prepare actionable regression findings.

## Inputs

Required:

- Stress corpus location outside the repository.
- Board set or explicit board list.
- Test mode and resource limits.

Optional: comparison revision, result-set name, concurrency, and issue-reporting scope.

This workflow is expensive and must be explicitly invoked.

## Codex and existing harness modes

The existing `tests/stress/run_queue.sh` harness launches headless Claude workers. Running it tests the existing Claude-based harness; it does not make Codex the worker.

For Codex-native testing, use one of these modes:

- `single-board`: Codex follows `tests/stress/RUNBOOK.md` for one board and writes the expected results JSON.
- `small-batch`: Codex runs an explicit small board list sequentially or with carefully bounded parallel tasks.
- `existing-harness`: run the current queue scripts only when the user explicitly wants to exercise the Claude-based harness.

Do not silently invoke `claude -p` from a Codex workflow.

## Procedure

1. Keep all downloaded boards, normalized boards, stripped boards, run directories, transcripts, and results outside the repository under `$STRESS_DIR`.
2. Reuse an existing validated corpus when possible. Otherwise prepare and validate it with the scripts under `tests/stress/`.
3. Read `tests/stress/RUNBOOK.md` before routing any board.
4. Apply per-command memory and runtime guards. Treat crashes, hangs, and resource-limit kills as findings.
5. For each board, record exact commands, staged outputs, structured summaries, DRC, connectivity, orphan stubs, elapsed time, and failure evidence.
6. Verify fanout summaries and full copper-layer lists on multilayer boards before signal routing.
7. Write results in the schema expected by the stress aggregation scripts.
8. Aggregate completion, multipoint connectivity, DRC baseline/final/delta, overall connectivity, orphan stubs, runtime, and issues.
9. Deduplicate findings against existing issues.
10. Present issue drafts and obtain explicit approval before creating, reopening, or commenting on GitHub issues.

## Output contract

Provide:

1. Corpus and revision information.
2. Board summary table sorted by completion or severity.
3. Crashes, hangs, resource failures, and correctness regressions.
4. Distinct deduplicated findings with reproduction commands and evidence.
5. Existing issues matched and proposed action.
6. Issue drafts awaiting approval or approved issue links.
7. Corpus preparation problems and untested boards.

Never commit corpus or generated artifacts to the repository.

## Technical reference

Use `.claude/skills/stress-test-router/SKILL.md` and `tests/stress/RUNBOOK.md` for corpus preparation, result schema, operational limits, aggregation, and known findings. Treat Claude queue-worker instructions as `existing-harness` behavior, not Codex-native execution.
