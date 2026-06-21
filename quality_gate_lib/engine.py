from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from quality_gate_lib.config import deep_get, load_quality_gate_config
from quality_gate_lib.coverage import read_coverage
from quality_gate_lib.documentation import analyze_documentation
from quality_gate_lib.models import Finding, GateResult
from quality_gate_lib.scanner import count_file_lines, find_functions, iter_source_files


def calculate_score(findings: List[Finding], coverage: Optional[float], min_coverage: float) -> int:
    score = 100
    for finding in findings:
        if finding.severity == "error":
            score -= 15
        elif finding.severity == "warning":
            score -= 5

    if coverage is not None and coverage < min_coverage:
        score -= int(min(30, min_coverage - coverage))

    return max(0, min(100, score))


def run_quality_gate(config_path: Path, explicit_root: Optional[str] = None, profile_name: Optional[str] = None) -> GateResult:
    config = load_quality_gate_config(config_path, profile_name=profile_name)
    root = Path(explicit_root or deep_get(config, "project.root", ".")).resolve()

    max_lines = int(deep_get(config, "thresholds.max_lines_per_file", 400))
    warn_lines = int(deep_get(config, "thresholds.warn_lines_per_file", 250))
    max_dup = int(deep_get(config, "thresholds.max_function_duplicates_allowed", 0))
    max_files_over = int(deep_get(config, "thresholds.max_files_over_line_limit_allowed", 0))
    min_coverage = float(deep_get(config, "thresholds.min_coverage_percent", 80))
    max_total_files = int(deep_get(config, "thresholds.max_total_files_scanned", 5000))
    ignore_function_names = set(deep_get(config, "rules.duplicated_functions.ignore_names", []))

    findings: List[Finding] = []
    files = list(iter_source_files(root, config))

    if len(files) > max_total_files:
        findings.append(
            Finding(
                rule="scan.max_total_files",
                severity="error",
                message=f"Total de arquivos escaneados excede o limite configurado: {len(files)} > {max_total_files}",
                value=len(files),
                threshold=max_total_files,
            )
        )
        files = files[:max_total_files]

    file_line_counts: Dict[str, int] = {}
    files_over_limit = 0

    if deep_get(config, "rules.file_lines.enabled", True):
        for file_path in files:
            rel = str(file_path.relative_to(root))
            lines = count_file_lines(file_path)
            file_line_counts[rel] = lines

            if lines > max_lines:
                files_over_limit += 1
                findings.append(
                    Finding(
                        rule="file.max_lines",
                        severity="error",
                        message=f"Arquivo excede limite de linhas: {lines} > {max_lines}",
                        file=rel,
                        value=lines,
                        threshold=max_lines,
                    )
                )
            elif lines > warn_lines:
                findings.append(
                    Finding(
                        rule="file.warn_lines",
                        severity="warning",
                        message=f"Arquivo está próximo de ficar grande demais: {lines} > {warn_lines}",
                        file=rel,
                        value=lines,
                        threshold=warn_lines,
                    )
                )

    if files_over_limit > max_files_over:
        findings.append(
            Finding(
                rule="file.max_files_over_line_limit",
                severity="error",
                message=f"Quantidade de arquivos acima do limite excedida: {files_over_limit} > {max_files_over}",
                value=files_over_limit,
                threshold=max_files_over,
            )
        )

    duplicate_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    total_functions = 0

    if deep_get(config, "rules.duplicated_functions.enabled", True):
        for file_path in files:
            for fn in find_functions(file_path, root):
                total_functions += 1
                if fn["name"] in ignore_function_names:
                    continue
                duplicate_groups[fn["signature"]].append(fn)

        duplicated = {sig: occ for sig, occ in duplicate_groups.items() if len(occ) > 1}
        duplicate_count = len(duplicated)

        if duplicate_count > max_dup:
            for signature, occurrences in duplicated.items():
                locations = ", ".join(f'{o["file"]}:{o["line"]}' for o in occurrences[:10])
                findings.append(
                    Finding(
                        rule="function.duplicate_signature",
                        severity="error",
                        message=f"Função/método aparentemente repetido: {signature}. Ocorrências: {locations}",
                        value=len(occurrences),
                        threshold=max_dup,
                    )
                )

    coverage = read_coverage(root, config)
    coverage_percent = coverage.get("coverage_percent")
    fail_if_missing = bool(deep_get(config, "coverage.fail_if_missing", False))
    documentation, documentation_findings = analyze_documentation(root, config)
    findings.extend(documentation_findings)

    if coverage.get("enabled"):
        if coverage.get("missing") and fail_if_missing:
            findings.append(
                Finding(
                    rule="coverage.missing",
                    severity="error",
                    message="Coverage habilitado, mas nenhum arquivo de coverage configurado foi encontrado.",
                    threshold=f">= {min_coverage}%",
                )
            )
        elif coverage_percent is not None and coverage_percent < min_coverage:
            findings.append(
                Finding(
                    rule="coverage.minimum",
                    severity="error",
                    message=f"Coverage abaixo do mínimo: {coverage_percent}% < {min_coverage}%",
                    value=coverage_percent,
                    threshold=min_coverage,
                )
            )

    score = calculate_score(findings, coverage_percent, min_coverage)
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    passed = errors == 0

    summary = {
        "project": deep_get(config, "project.name", root.name),
        "root": str(root),
        "files_scanned": len(files),
        "total_functions_detected": total_functions,
        "files_over_line_limit": files_over_limit,
        "coverage": coverage,
        "documentation": documentation,
        "errors": errors,
        "warnings": warnings,
        "score": score,
        "passed": passed,
        "quality_dimensions": {
            "readability": "limite de linhas por arquivo e alertas de arquivos grandes",
            "maintainability": "funções repetidas e modularidade por tamanho de arquivo",
            "reliability_security": "coverage mínimo e falha controlada no gate",
            "modularity": "arquivos menores e funções menos duplicadas",
            "efficiency": "controle do volume escaneado e higiene de baseline",
            "documentation_readability": "documentação concisa, com títulos e seções fáceis de revisar no PR",
        },
        "profile": profile_name or config.get("profile") or deep_get(config, "project.profile"),
    }

    return GateResult(passed=passed, score=score, summary=summary, findings=findings)
