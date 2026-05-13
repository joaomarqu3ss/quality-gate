import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Optional

from quality_gate_lib.config import deep_get


def parse_lcov(path: Path) -> Optional[float]:
    found = hit = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("LF:"):
                found += int(line.split(":", 1)[1])
            elif line.startswith("LH:"):
                hit += int(line.split(":", 1)[1])
    except Exception:
        return None
    if found == 0:
        return None
    return (hit / found) * 100


def parse_cobertura_or_jacoco(path: Path) -> Optional[float]:
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return None

    line_rate = root.attrib.get("line-rate")
    if line_rate is not None:
        try:
            return float(line_rate) * 100
        except ValueError:
            pass

    total_missed = total_covered = 0
    for counter in root.iter("counter"):
        if counter.attrib.get("type") == "LINE":
            total_missed += int(counter.attrib.get("missed", "0"))
            total_covered += int(counter.attrib.get("covered", "0"))

    total = total_missed + total_covered
    if total > 0:
        return (total_covered / total) * 100

    return None


def read_coverage(root: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    coverage_enabled = deep_get(config, "coverage.enabled", True) and deep_get(config, "rules.coverage.enabled", True)
    if not coverage_enabled:
        return {"enabled": False, "coverage_percent": None, "source": None, "missing": False}

    coverage_paths = deep_get(config, "coverage.paths", [])
    for relative in coverage_paths:
        candidate = root / relative
        if not candidate.exists():
            continue

        if candidate.name == "lcov.info" or candidate.suffix.lower() == ".info":
            percent = parse_lcov(candidate)
        elif candidate.suffix.lower() == ".xml":
            percent = parse_cobertura_or_jacoco(candidate)
        else:
            percent = None

        if percent is not None:
            return {
                "enabled": True,
                "coverage_percent": round(percent, 2),
                "source": str(candidate.relative_to(root)),
                "missing": False,
            }

    return {"enabled": True, "coverage_percent": None, "source": None, "missing": True}
