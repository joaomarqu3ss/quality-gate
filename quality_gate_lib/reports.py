import dataclasses
import json
from pathlib import Path
from typing import Optional, Tuple

from quality_gate_lib.config import deep_get, load_quality_gate_config
from quality_gate_lib.models import GateResult
from quality_gate_lib.report_renderers import (
    coverage_text,
    documentation_text,
    render_html_report,
    render_markdown_report,
)


def resolve_report_paths(
    config_path: Path,
    explicit_root: Optional[str] = None,
    profile_name: Optional[str] = None,
) -> Tuple[Path, Path, Path]:
    config = load_quality_gate_config(config_path, profile_name=profile_name)
    root = Path(explicit_root or deep_get(config, "project.root", ".")).resolve()
    output_dir = root / deep_get(config, "reports.output_dir", "quality-gate-report")

    json_path = output_dir / deep_get(config, "reports.json_file", "quality-gate-report.json")
    html_path = output_dir / deep_get(config, "reports.html_file", "quality-gate-report.html")
    markdown_path = output_dir / deep_get(config, "reports.markdown_file", "quality-gate-report.md")
    return json_path, html_path, markdown_path


def write_reports(
    result: GateResult,
    config_path: Path,
    explicit_root: Optional[str] = None,
    profile_name: Optional[str] = None,
) -> Tuple[Path, Path]:
    json_path, html_path, markdown_path = resolve_report_paths(config_path, explicit_root, profile_name)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "passed": result.passed,
        "score": result.score,
        "summary": result.summary,
        "findings": [dataclasses.asdict(f) for f in result.findings],
    }

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown_report(result, html_path, json_path), encoding="utf-8")
    html_path.write_text(render_html_report(result), encoding="utf-8")
    return json_path, html_path


def print_console_summary(
    result: GateResult,
    json_path: Path,
    html_path: Path,
    markdown_path: Optional[Path] = None,
) -> None:
    status = "PASSOU" if result.passed else "FALHOU"
    icon = "[PASS]" if result.passed else "[FAIL]"

    print(f"\n{icon} QUALITY GATE: {status}")
    print(f"Score: {result.score}/100")
    print(f"Arquivos escaneados: {result.summary['files_scanned']}")
    print(f"Funções detectadas: {result.summary['total_functions_detected']}")
    print(f"Erros: {result.summary['errors']} | Warnings: {result.summary['warnings']}")

    print(f"Coverage: {coverage_text(result)}")
    print(f"Documentação: {documentation_text(result)}")

    if result.findings:
        print("\nPrincipais findings:")
        for finding in result.findings[:20]:
            if finding.file and finding.line:
                location = f" [{finding.file}:{finding.line}]"
            elif finding.file:
                location = f" [{finding.file}]"
            else:
                location = ""
            print(f"- {finding.severity.upper()} {finding.rule}{location}: {finding.message}")

        if len(result.findings) > 20:
            print(f"... e mais {len(result.findings) - 20} findings.")

    print(f"\nRelatório JSON: {json_path}")
    print(f"Relatório HTML: {html_path}\n")
    if markdown_path:
        print(f"Relatório Markdown: {markdown_path}\n")
