"""Normalized result model for the local JLC manufacturing preflight."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str  # error | warning | info
    message: str
    measured: Optional[float] = None
    required: Optional[float] = None
    unit: str = "mm"
    objects: Tuple[str, ...] = ()
    location: Optional[Tuple[float, float]] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # JSON is friendlier with arrays than tuples.
        data["objects"] = list(self.objects)
        if self.location is not None:
            data["location"] = list(self.location)
        # Keep reports compact and stable for AI consumption.
        return {k: v for k, v in data.items() if v not in (None, (), {}, [])}


@dataclass
class DfmReport:
    source: str
    profile: Dict[str, Any]
    inputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tool: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)
    coverage: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    schema_version: str = "2"
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @property
    def errors(self) -> Sequence[Finding]:
        return tuple(f for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> Sequence[Finding]:
        return tuple(f for f in self.findings if f.severity == "warning")

    @property
    def infos(self) -> Sequence[Finding]:
        return tuple(f for f in self.findings if f.severity == "info")

    @property
    def status(self) -> str:
        if self.errors:
            return "fail"
        if self.warnings:
            return "review_required"
        return "pass"

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> Dict[str, Any]:
        finding_dicts = [f.to_dict() for f in self.findings]
        by_rule: Dict[str, int] = {}
        for finding in self.findings:
            by_rule[finding.rule] = by_rule.get(finding.rule, 0) + 1
        stable = {
            "schema_version": self.schema_version,
            "source": self.source,
            "inputs": self.inputs,
            "tool": self.tool,
            "profile": self.profile,
            "metrics": self.metrics,
            "coverage": self.coverage,
            "limitations": self.limitations,
            "findings": finding_dicts,
        }
        fingerprint_stable = dict(stable)
        fingerprint_stable.pop("source", None)
        fingerprint_stable["inputs"] = {
            name: {k: v for k, v in evidence.items() if k != "path"}
            for name, evidence in self.inputs.items()
        }
        fingerprint = hashlib.sha256(json.dumps(
            fingerprint_stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest().upper()
        return {
            **stable,
            "generated_at": self.generated_at,
            "evidence_fingerprint_sha256": fingerprint,
            "summary": {
                "status": self.status,
                "passed": self.passed,
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "info": len(self.infos),
                "findings": len(self.findings),
                "by_rule": dict(sorted(by_rule.items())),
            },
        }
