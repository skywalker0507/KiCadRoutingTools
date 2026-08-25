"""Normalized result model for the local JLC manufacturing preflight."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
    findings: List[Finding] = field(default_factory=list)
    coverage: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    schema_version: str = "1"
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
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "source": self.source,
            "profile": self.profile,
            "summary": {
                "passed": self.passed,
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "findings": len(self.findings),
            },
            "coverage": self.coverage,
            "limitations": self.limitations,
            "findings": [f.to_dict() for f in self.findings],
        }
