import fnmatch
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from quality_gate_lib.config import deep_get
from quality_gate_lib.models import Finding


MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+\S")


def iter_documentation_files(root: Path, config: Dict[str, Any]) -> Iterable[Path]:
    include_ext = set(deep_get(config, "documentation.include_extensions", [".md", ".markdown"]))
    exclude_dirs = deep_get(config, "documentation.exclude_dirs", [])
    exclude_files = deep_get(config, "documentation.exclude_files", [])

    for current_root, dirs, files in os.walk(root):
        current_path = Path(current_root)
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        if any(excluded in set(current_path.parts) for excluded in exclude_dirs):
            continue

        for file_name in files:
            file_path = current_path / file_name
            if any(fnmatch.fnmatch(file_path.name, pattern) for pattern in exclude_files):
                continue
            if file_path.suffix.lower() in include_ext:
                yield file_path


def markdown_headings(lines: List[str]) -> List[Tuple[int, int]]:
    headings: List[Tuple[int, int]] = []
    in_fence = False

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        match = MARKDOWN_HEADING_RE.match(line)
        if match:
            headings.append((index, len(match.group(1))))

    return headings


def analyze_documentation_file(file_path: Path, root: Path, config: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Finding]]:
    max_lines = int(deep_get(config, "documentation.max_lines_per_doc", 300))
    max_section_lines = int(deep_get(config, "documentation.max_section_lines", 120))
    max_heading_depth = int(deep_get(config, "documentation.max_heading_depth", 4))
    require_h1 = bool(deep_get(config, "documentation.require_h1", True))
    findings: List[Finding] = []
    docs_over_line_limit = 0
    sections_over_limit = 0
    docs_missing_h1 = 0
    docs_with_deep_headings = 0

    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return {"files_scanned": 0}, []

    rel = str(file_path.relative_to(root))
    line_count = len(lines)
    if line_count > max_lines:
        docs_over_line_limit += 1
        findings.append(
            Finding(
                rule="documentation.max_lines",
                severity="warning",
                message=f"Documentação longa demais para revisão rápida: {line_count} > {max_lines} linhas",
                file=rel,
                value=line_count,
                threshold=max_lines,
            )
        )

    headings = markdown_headings(lines)
    if require_h1 and not any(level == 1 for _, level in headings):
        docs_missing_h1 += 1
        findings.append(
            Finding(
                rule="documentation.missing_h1",
                severity="warning",
                message="Documentação sem título H1; isso reduz a clareza do resumo no PR.",
                file=rel,
                threshold="H1 obrigatório",
            )
        )

    deep_heading_lines = [line for line, level in headings if level > max_heading_depth]
    if deep_heading_lines:
        docs_with_deep_headings += 1
        findings.append(
            Finding(
                rule="documentation.heading_depth",
                severity="warning",
                message=f"Documentação usa heading profundo demais: H{max_heading_depth + 1}+",
                file=rel,
                line=deep_heading_lines[0],
                threshold=f"até H{max_heading_depth}",
            )
        )

    for index, (heading_line, _) in enumerate(headings):
        next_line = headings[index + 1][0] if index + 1 < len(headings) else line_count + 1
        section_lines = next_line - heading_line - 1
        if section_lines > max_section_lines:
            sections_over_limit += 1
            findings.append(
                Finding(
                    rule="documentation.section_length",
                    severity="warning",
                    message=f"Seção longa demais para leitura no PR: {section_lines} > {max_section_lines} linhas",
                    file=rel,
                    line=heading_line,
                    value=section_lines,
                    threshold=max_section_lines,
                )
            )

    summary = {
        "files_scanned": 1,
        "docs_over_line_limit": docs_over_line_limit,
        "sections_over_limit": sections_over_limit,
        "docs_missing_h1": docs_missing_h1,
        "docs_with_deep_headings": docs_with_deep_headings,
        "max_lines_per_doc": max_lines,
        "max_section_lines": max_section_lines,
        "max_heading_depth": max_heading_depth,
    }
    return summary, findings


def analyze_documentation(root: Path, config: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Finding]]:
    enabled = deep_get(config, "documentation.enabled", True) and deep_get(
        config,
        "rules.documentation.enabled",
        True,
    )
    if not enabled:
        return {"enabled": False, "files_scanned": 0}, []

    files = list(iter_documentation_files(root, config))
    findings: List[Finding] = []
    summary = {
        "enabled": True,
        "files_scanned": len(files),
        "docs_over_line_limit": 0,
        "sections_over_limit": 0,
        "docs_missing_h1": 0,
        "docs_with_deep_headings": 0,
        "max_lines_per_doc": int(deep_get(config, "documentation.max_lines_per_doc", 300)),
        "max_section_lines": int(deep_get(config, "documentation.max_section_lines", 120)),
        "max_heading_depth": int(deep_get(config, "documentation.max_heading_depth", 4)),
    }

    for file_path in files:
        file_summary, file_findings = analyze_documentation_file(file_path, root, config)
        findings.extend(file_findings)
        for key in ("docs_over_line_limit", "sections_over_limit", "docs_missing_h1", "docs_with_deep_headings"):
            summary[key] += int(file_summary.get(key, 0))

    return summary, findings
