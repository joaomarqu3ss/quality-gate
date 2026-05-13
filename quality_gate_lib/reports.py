import dataclasses
import html
import json
from pathlib import Path
from typing import Optional, Tuple

from quality_gate_lib.config import deep_get, load_quality_gate_config
from quality_gate_lib.models import GateResult


def write_reports(
    result: GateResult,
    config_path: Path,
    explicit_root: Optional[str] = None,
    profile_name: Optional[str] = None,
) -> Tuple[Path, Path]:
    config = load_quality_gate_config(config_path, profile_name=profile_name)
    root = Path(explicit_root or deep_get(config, "project.root", ".")).resolve()
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
    icon = "[PASS]" if result.passed else "[FAIL]"

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
