import dataclasses
from typing import Any, Dict, List, Optional


@dataclasses.dataclass
class Finding:
    rule: str
    severity: str
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    value: Optional[Any] = None
    threshold: Optional[Any] = None


@dataclasses.dataclass
class GateResult:
    passed: bool
    score: int
    summary: Dict[str, Any]
    findings: List[Finding]
