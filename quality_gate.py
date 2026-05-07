#!/usr/bin/env python3
"""
Quality Gate Baseline

Script para bloquear ou aprovar uma baseline de código com base em métricas configuráveis.

Recursos principais:
- Limite de linhas por arquivo.
- Detecção simples de funções/métodos repetidos por nome e assinatura aproximada.
- Detecção de arquivos muito grandes.
- Integração com coverage em formatos comuns:
  - lcov.info para JavaScript/TypeScript/Angular.
  - cobertura.xml para Python e várias ferramentas.
  - jacoco.xml para Java/Spring Boot.
- Geração de relatório JSON e HTML.
- Arquivo de métricas externo e manipulável: quality-gate.yml.

Uso:
  python quality_gate.py --config quality-gate.yml
  python quality_gate.py --config quality-gate.yml --root .
  python quality_gate.py --init-config
"""

from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_CONFIG = """# quality-gate.yml
# Métricas padrão manipuláveis para o Quality Gate.
# Ajuste os valores conforme a maturidade do seu projeto.

project:
  name: "my-project"
  root: "."
  baseline_mode: true

scan:
  include_extensions:
    - ".java"
    - ".kt"
    - ".js"
    - ".jsx"
    - ".ts"
    - ".tsx"
    - ".py"
    - ".go"
    - ".cs"
  exclude_dirs:
    - ".git"
    - "node_modules"
    - "dist"
    - "build"
    - "coverage"
    - "target"
    - ".angular"
    - ".idea"
    - ".vscode"
    - "__pycache__"
  exclude_files:
    - "*.min.js"
    - "*.bundle.js"
    - "*.generated.*"
    - "*.g.dart"

thresholds:
  # Readability / Maintainability
  max_lines_per_file: 400
  max_function_duplicates_allowed: 0
  max_files_over_line_limit_allowed: 0

  # Reliability
  min_coverage_percent: 80

  # Modularity
  warn_lines_per_file: 250

  # Efficiency / Hygiene
  max_total_files_scanned: 5000

coverage:
  enabled: true
  # Exemplos:
  # Angular/JS/TS: coverage/lcov.info
  # Java/Jacoco: target/site/jacoco/jacoco.xml
  # Python/Cobertura: coverage.xml
  paths:
    - "coverage/lcov.info"
    - "coverage/lcov-report/lcov.info"
    - "target/site/jacoco/jacoco.xml"
    - "coverage.xml"
  fail_if_missing: false

reports:
  output_dir: "quality-gate-report"
  json_file: "quality-gate-report.json"
  html_file: "quality-gate-report.html"

rules:
  duplicated_functions:
    enabled: true
    # Nomes muito comuns podem gerar falso positivo em alguns projetos.
    ignore_names:
      - "toString"
      - "equals"
      - "hashCode"
      - "constructor"
      - "ngOnInit"
      - "ngOnDestroy"

  file_lines:
    enabled: true

  coverage:
    enabled: true
"""


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


def load_yaml_or_fallback(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        print(
            "ERRO: PyYAML não encontrado. Instale com: pip install pyyaml",
            file=sys.stderr,
        )
        sys.exit(2)

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return data


def deep_get(data: Dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    current: Any = data
    for key in dotted_path.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def should_exclude_dir(path: Path, exclude_dirs: List[str]) -> bool:
    parts = set(path.parts)
    return any(excluded in parts for excluded in exclude_dirs)


def should_exclude_file(path: Path, exclude_files: List[str]) -> bool:
    name = path.name
    return any(fnmatch.fnmatch(name, pattern) for pattern in exclude_files)


def iter_source_files(root: Path, config: Dict[str, Any]) -> Iterable[Path]:
    include_ext = set(deep_get(config, "scan.include_extensions", []))
    exclude_dirs = deep_get(config, "scan.exclude_dirs", [])
    exclude_files = deep_get(config, "scan.exclude_files", [])

    for current_root, dirs, files in os.walk(root):
        current_path = Path(current_root)

        # Remove diretórios excluídos antes de descer.
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        if should_exclude_dir(current_path, exclude_dirs):
            continue

        for file_name in files:
            file_path = current_path / file_name
            if should_exclude_file(file_path, exclude_files):
                continue
            if file_path.suffix.lower() in include_ext:
                yield file_path


def count_file_lines(file_path: Path) -> int:
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


FUNCTION_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "js_ts_function",
        re.compile(
            r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)",
            re.MULTILINE,
        ),
    ),
    (
        "js_ts_arrow_const",
        re.compile(
            r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>",
            re.MULTILINE,
        ),
    ),
    (
        "js_ts_method",
        re.compile(
            r"^\s*(?:public|private|protected|static|async|override|readonly|\s)*\s*([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?::\s*[^={]+)?\s*\{",
            re.MULTILINE,
        ),
    ),
    (
        "python_def",
        re.compile(
            r"^\s*def\s+([A-Za-z_][\w]*)\s*\(([^)]*)\)\s*:",
            re.MULTILINE,
        ),
    ),
    (
        "java_method",
        re.compile(
            r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?[\w<>\[\], ?]+\s+([A-Za-z_][\w]*)\s*\(([^)]*)\)\s*(?:throws\s+[\w,\s]+)?\s*\{",
            re.MULTILINE,
        ),
    ),
    (
        "go_func",
        re.compile(
            r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_][\w]*)\s*\(([^)]*)\)",
            re.MULTILINE,
        ),
    ),
    (
        "csharp_method",
        re.compile(
            r"^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?(?:async\s+)?[\w<>\[\], ?]+\s+([A-Za-z_][\w]*)\s*\(([^)]*)\)\s*\{",
            re.MULTILINE,
        ),
    ),
]


def normalize_params(params: str) -> str:
    # Normalização leve para comparar assinaturas aproximadas.
    params = re.sub(r"\s+", " ", params.strip())
    if not params:
        return ""
    parts = [p.strip() for p in params.split(",") if p.strip()]
    normalized = []
    for p in parts:
        # Remove valores default e nomes comuns quando possível.
        p = p.split("=")[0].strip()
        p = re.sub(r"\b(final|readonly|public|private|protected)\b", "", p).strip()
        normalized.append(p)
    return ",".join(normalized)


def find_functions(file_path: Path, root: Path) -> List[Dict[str, Any]]:
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    functions: List[Dict[str, Any]] = []
    for pattern_name, pattern in FUNCTION_PATTERNS:
        for match in pattern.finditer(content):
            name = match.group(1)
            params = normalize_params(match.group(2) if match.lastindex and match.lastindex >= 2 else "")
            line = content.count("\n", 0, match.start()) + 1

            # Evita falsos positivos comuns em controle de fluxo.
            if name in {"if", "for", "while", "switch", "catch", "return"}:
                continue

            functions.append(
                {
                    "name": name,
                    "signature": f"{name}({params})",
                    "pattern": pattern_name,
                    "file": str(file_path.relative_to(root)),
                    "line": line,
                }
            )

    return functions


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

    # Cobertura: <coverage line-rate="0.83">
    line_rate = root.attrib.get("line-rate")
    if line_rate is not None:
        try:
            return float(line_rate) * 100
        except ValueError:
            pass

    # JaCoCo: <counter type="LINE" missed="10" covered="90"/>
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

        if candidate.name == "lcov.info":
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


def run_quality_gate(config_path: Path, explicit_root: Optional[str] = None) -> GateResult:
    config = load_yaml_or_fallback(config_path)
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

    # Regra: limite de linhas por arquivo.
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

    # Regra: funções repetidas.
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

    # Regra: coverage.
    coverage = read_coverage(root, config)
    coverage_percent = coverage.get("coverage_percent")
    fail_if_missing = bool(deep_get(config, "coverage.fail_if_missing", False))

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
        },
    }

    return GateResult(passed=passed, score=score, summary=summary, findings=findings)


def write_reports(result: GateResult, config_path: Path) -> Tuple[Path, Path]:
    config = load_yaml_or_fallback(config_path)
    root = Path(deep_get(config, "project.root", ".")).resolve()
    output_dir = root / deep_get(config, "reports.output_dir", "quality-gate-report")
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / deep_get(config, "reports.json_file", "quality-gate-report.json")
    html_path = output_dir / deep_get(config, "reports.html_file", "quality-gate-report.html")

    payload = {
        "passed": result.passed,
        "score": result.score,
        "summary": result.summary,
        "findings": [dataclasses.asdict(f) for f in result.findings],
    }

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = []
    for finding in result.findings:
        rows.append(
            "<tr>"
            f"<td>{html.escape(finding.severity)}</td>"
            f"<td>{html.escape(finding.rule)}</td>"
            f"<td>{html.escape(finding.file or '-')}</td>"
            f"<td>{html.escape(str(finding.line or '-'))}</td>"
            f"<td>{html.escape(finding.message)}</td>"
            "</tr>"
        )

    status = "PASSOU" if result.passed else "FALHOU"
    coverage = result.summary.get("coverage", {})
    coverage_text = "-"
    if coverage.get("coverage_percent") is not None:
        coverage_text = f'{coverage["coverage_percent"]}% ({coverage.get("source")})'
    elif coverage.get("missing"):
        coverage_text = "não encontrado"

    html_doc = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Quality Gate Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #222; }}
    .card {{ border: 1px solid #ddd; border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
    .pass {{ color: #0a7f27; }}
    .fail {{ color: #b00020; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #eee; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f7f7f7; }}
    code {{ background: #f2f2f2; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Quality Gate Report</h1>
  <div class="card">
    <h2 class="{"pass" if result.passed else "fail"}">{status}</h2>
    <p><strong>Score:</strong> {result.score}/100</p>
    <p><strong>Projeto:</strong> {html.escape(str(result.summary.get("project")))}</p>
    <p><strong>Arquivos escaneados:</strong> {result.summary.get("files_scanned")}</p>
    <p><strong>Funções detectadas:</strong> {result.summary.get("total_functions_detected")}</p>
    <p><strong>Coverage:</strong> {html.escape(coverage_text)}</p>
    <p><strong>Erros:</strong> {result.summary.get("errors")} | <strong>Warnings:</strong> {result.summary.get("warnings")}</p>
  </div>

  <h2>Findings</h2>
  <table>
    <thead>
      <tr>
        <th>Severidade</th>
        <th>Regra</th>
        <th>Arquivo</th>
        <th>Linha</th>
        <th>Mensagem</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows) if rows else '<tr><td colspan="5">Nenhum problema encontrado.</td></tr>'}
    </tbody>
  </table>
</body>
</html>
"""

    html_path.write_text(html_doc, encoding="utf-8")
    return json_path, html_path


def print_console_summary(result: GateResult, json_path: Path, html_path: Path) -> None:
    status = "PASSOU" if result.passed else "FALHOU"
    icon = "✅" if result.passed else "❌"

    print(f"\n{icon} QUALITY GATE: {status}")
    print(f"Score: {result.score}/100")
    print(f"Arquivos escaneados: {result.summary['files_scanned']}")
    print(f"Funções detectadas: {result.summary['total_functions_detected']}")
    print(f"Erros: {result.summary['errors']} | Warnings: {result.summary['warnings']}")

    coverage = result.summary.get("coverage", {})
    if coverage.get("coverage_percent") is not None:
        print(f"Coverage: {coverage['coverage_percent']}% ({coverage.get('source')})")
    elif coverage.get("missing"):
        print("Coverage: não encontrado")
    else:
        print("Coverage: desabilitado")

    if result.findings:
        print("\nPrincipais findings:")
        for finding in result.findings[:20]:
            location = f" [{finding.file}:{finding.line}]" if finding.file and finding.line else f" [{finding.file}]" if finding.file else ""
            print(f"- {finding.severity.upper()} {finding.rule}{location}: {finding.message}")

        if len(result.findings) > 20:
            print(f"... e mais {len(result.findings) - 20} findings.")

    print(f"\nRelatório JSON: {json_path}")
    print(f"Relatório HTML: {html_path}\n")


def init_config(path: Path) -> None:
    if path.exists():
        print(f"Arquivo já existe: {path}")
        return
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    print(f"Configuração criada em: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Quality Gate Baseline para projetos de código.")
    parser.add_argument("--config", default="quality-gate.yml", help="Caminho para o arquivo YAML de métricas.")
    parser.add_argument("--root", default=None, help="Raiz do projeto a ser escaneado. Sobrescreve project.root.")
    parser.add_argument("--init-config", action="store_true", help="Cria um quality-gate.yml padrão.")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()

    if args.init_config:
        init_config(config_path)
        return 0

    if not config_path.exists():
        print(f"Config não encontrado: {config_path}", file=sys.stderr)
        print("Crie um config com: python quality_gate.py --init-config", file=sys.stderr)
        return 2

    result = run_quality_gate(config_path, explicit_root=args.root)
    json_path, html_path = write_reports(result, config_path)
    print_console_summary(result, json_path, html_path)

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
