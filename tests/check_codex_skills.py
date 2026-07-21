#!/usr/bin/env python3
"""Validate repository-scoped Codex skill structure without external dependencies."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / ".agents" / "skills"

EXPECTED_SKILLS = {
    "plan-pcb-routing": "docs/agent-workflows/routing-plan.md",
    "analyze-power-nets": "docs/agent-workflows/power-net-analysis.md",
    "find-high-speed-nets": "docs/agent-workflows/high-speed-analysis.md",
    "identify-diff-pairs": "docs/agent-workflows/diff-pair-analysis.md",
    "recommend-plane-mappings": "docs/agent-workflows/plane-mapping.md",
    "recommend-stackup": "docs/agent-workflows/stackup-review.md",
    "diagnose-routing-failures": "docs/agent-workflows/failure-diagnosis.md",
    "review-routed-board": "docs/agent-workflows/board-review.md",
    "stress-test-router": "docs/agent-workflows/stress-testing.md",
}

BANNED_LEGACY_PHRASES = (
    "# Codex Adapter:",
    "The canonical workflow is `.claude/skills/",
    "read that file in full and follow it as the source of truth",
)


def parse_front_matter(text: str, path: Path) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path}: missing opening YAML front matter delimiter")

    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"{path}: missing closing YAML front matter delimiter") from exc

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_-]+):\s*(.+)", line)
        if not match:
            raise ValueError(f"{path}: unsupported front matter line: {line!r}")
        key, value = match.groups()
        metadata[key] = value.strip().strip('"').strip("'")
    return metadata


def validate_skill(name: str, workflow_path: str) -> list[str]:
    errors: list[str] = []
    skill_path = SKILLS_ROOT / name / "SKILL.md"
    if not skill_path.is_file():
        return [f"missing skill file: {skill_path.relative_to(ROOT)}"]

    text = skill_path.read_text(encoding="utf-8")
    try:
        metadata = parse_front_matter(text, skill_path)
    except ValueError as exc:
        return [str(exc)]

    if metadata.get("name") != name:
        errors.append(
            f"{skill_path.relative_to(ROOT)}: front matter name "
            f"{metadata.get('name')!r} does not match directory {name!r}"
        )

    description = metadata.get("description", "").strip()
    if not description:
        errors.append(f"{skill_path.relative_to(ROOT)}: missing description")

    if workflow_path not in text:
        errors.append(
            f"{skill_path.relative_to(ROOT)}: does not reference {workflow_path}"
        )

    if not (ROOT / workflow_path).is_file():
        errors.append(f"missing shared workflow: {workflow_path}")

    for phrase in BANNED_LEGACY_PHRASES:
        if phrase in text:
            errors.append(
                f"{skill_path.relative_to(ROOT)}: contains legacy adapter phrase {phrase!r}"
            )

    return errors


def main() -> int:
    errors: list[str] = []

    common_workflow = ROOT / "docs" / "agent-workflows" / "README.md"
    if not common_workflow.is_file():
        errors.append("missing docs/agent-workflows/README.md")

    actual_skills = {
        path.parent.name
        for path in SKILLS_ROOT.glob("*/SKILL.md")
        if path.is_file()
    }
    expected = set(EXPECTED_SKILLS)
    if actual_skills != expected:
        missing = sorted(expected - actual_skills)
        extra = sorted(actual_skills - expected)
        if missing:
            errors.append(f"missing expected skills: {', '.join(missing)}")
        if extra:
            errors.append(f"unexpected skills not in validator: {', '.join(extra)}")

    for name, workflow_path in EXPECTED_SKILLS.items():
        errors.extend(validate_skill(name, workflow_path))

    stress_metadata = (
        SKILLS_ROOT / "stress-test-router" / "agents" / "openai.yaml"
    )
    if not stress_metadata.is_file():
        errors.append("stress-test-router is missing agents/openai.yaml")
    else:
        metadata_text = stress_metadata.read_text(encoding="utf-8")
        if not re.search(r"allow_implicit_invocation:\s*false\b", metadata_text):
            errors.append(
                "stress-test-router must set allow_implicit_invocation: false"
            )

    if errors:
        print("Codex skill validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Codex skill validation passed: {len(EXPECTED_SKILLS)} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
