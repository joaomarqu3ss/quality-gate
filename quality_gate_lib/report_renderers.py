import html
from pathlib import Path

from quality_gate_lib.models import GateResult


def coverage_text(result: GateResult) -> str:
    coverage = result.summary.get("coverage", {})
    if coverage.get("coverage_percent") is not None:
        return f'{coverage["coverage_percent"]}% ({coverage.get("source")})'
    if coverage.get("missing"):
        return "não encontrado"
    return "desabilitado"


def documentation_text(result: GateResult) -> str:
    documentation = result.summary.get("documentation", {})
    if not documentation.get("enabled"):
        return "desabilitada"
    return (
        f'{documentation.get("files_scanned", 0)} docs, '
        f'{documentation.get("docs_over_line_limit", 0)} longos, '
        f'{documentation.get("sections_over_limit", 0)} seções longas'
    )


def escape_markdown_table(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown_report(result: GateResult, html_path: Path, json_path: Path) -> str:
    status = "PASSOU" if result.passed else "FALHOU"
    icon = "[PASS]" if result.passed else "[FAIL]"
    documentation = result.summary.get("documentation", {})

    lines = [
        "# Quality Gate Report",
        "",
        f"**Status:** {icon} {status}",
        "",
        "## Resumo",
        "",
        "| Métrica | Valor |",
        "| --- | --- |",
        f"| Score | {result.score}/100 |",
        f"| Projeto | {escape_markdown_table(result.summary.get('project', '-'))} |",
        f"| Profile | {escape_markdown_table(result.summary.get('profile') or '-')} |",
        f"| Arquivos escaneados | {result.summary.get('files_scanned')} |",
        f"| Funções detectadas | {result.summary.get('total_functions_detected')} |",
        f"| Coverage | {escape_markdown_table(coverage_text(result))} |",
        f"| Documentação | {escape_markdown_table(documentation_text(result))} |",
        f"| Erros | {result.summary.get('errors')} |",
        f"| Warnings | {result.summary.get('warnings')} |",
        "",
    ]

    if documentation.get("enabled"):
        lines.extend(
            [
                "## Documentação",
                "",
                "| Métrica | Valor |",
                "| --- | --- |",
                f"| Arquivos de documentação | {documentation.get('files_scanned', 0)} |",
                f"| Documentos longos | {documentation.get('docs_over_line_limit', 0)} |",
                f"| Seções longas | {documentation.get('sections_over_limit', 0)} |",
                f"| Sem H1 | {documentation.get('docs_missing_h1', 0)} |",
                f"| Headings profundos | {documentation.get('docs_with_deep_headings', 0)} |",
                "",
            ]
        )

    lines.extend(["## Findings", ""])
    if not result.findings:
        lines.append("Nenhum problema encontrado.")
    else:
        lines.extend(["| Severidade | Regra | Local | Mensagem |", "| --- | --- | --- | --- |"])
        for finding in result.findings[:50]:
            location = finding.file or "-"
            if finding.file and finding.line:
                location = f"{finding.file}:{finding.line}"
            lines.append(
                "| "
                f"{escape_markdown_table(finding.severity.upper())} | "
                f"{escape_markdown_table(finding.rule)} | "
                f"{escape_markdown_table(location)} | "
                f"{escape_markdown_table(finding.message)} |"
            )
        if len(result.findings) > 50:
            lines.append("")
            lines.append(f"_Mais {len(result.findings) - 50} findings no relatório HTML._")

    lines.extend(["", "## Artefatos", "", f"- HTML: `{html_path.name}`", f"- JSON: `{json_path.name}`"])
    return "\n".join(lines) + "\n"


def render_finding_rows(result: GateResult) -> str:
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
    return "".join(rows) if rows else '<tr><td colspan="5">Nenhum problema encontrado.</td></tr>'


def render_html_report(result: GateResult) -> str:
    status = "PASSOU" if result.passed else "FALHOU"
    documentation = result.summary.get("documentation", {})
    rows = render_finding_rows(result)

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Quality Gate Report</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ font-family: Arial, sans-serif; margin: 0; color: #1f2933; background: #f5f7fa; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px; }}
    .hero, section, .metric {{ background: #fff; border: 1px solid #d8dee8; border-radius: 8px; }}
    .hero {{ padding: 24px; margin-bottom: 16px; }}
    .hero h1 {{ margin: 0 0 8px; font-size: 28px; }}
    .status {{ font-weight: 700; }}
    .pass {{ color: #0b6b2b; }}
    .fail {{ color: #9f1239; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .metric {{ padding: 14px; }}
    .metric span {{ display: block; color: #5f6c7b; font-size: 12px; text-transform: uppercase; }}
    .metric strong {{ display: block; font-size: 20px; margin-top: 6px; }}
    section {{ padding: 18px; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #e6eaf0; padding: 9px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f7; color: #27313f; }}
    code {{ background: #eef2f7; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <main>
    <div class="hero">
      <h1>Quality Gate Report</h1>
      <p class="status {"pass" if result.passed else "fail"}">{status}</p>
      <p>Projeto: <strong>{html.escape(str(result.summary.get("project")))}</strong></p>
    </div>
    <div class="grid">
      <div class="metric"><span>Score</span><strong>{result.score}/100</strong></div>
      <div class="metric"><span>Arquivos</span><strong>{result.summary.get("files_scanned")}</strong></div>
      <div class="metric"><span>Funções</span><strong>{result.summary.get("total_functions_detected")}</strong></div>
      <div class="metric"><span>Coverage</span><strong>{html.escape(coverage_text(result))}</strong></div>
      <div class="metric"><span>Documentação</span><strong>{html.escape(documentation_text(result))}</strong></div>
      <div class="metric"><span>Findings</span><strong>{result.summary.get("errors")} erros / {result.summary.get("warnings")} warnings</strong></div>
    </div>
    <section>
      <h2>Documentação</h2>
      <table><tbody>
        <tr><th>Arquivos</th><td>{documentation.get("files_scanned", 0)}</td></tr>
        <tr><th>Documentos longos</th><td>{documentation.get("docs_over_line_limit", 0)}</td></tr>
        <tr><th>Seções longas</th><td>{documentation.get("sections_over_limit", 0)}</td></tr>
        <tr><th>Sem H1</th><td>{documentation.get("docs_missing_h1", 0)}</td></tr>
        <tr><th>Headings profundos</th><td>{documentation.get("docs_with_deep_headings", 0)}</td></tr>
      </tbody></table>
    </section>
    <section>
      <h2>Findings</h2>
      <table>
        <thead><tr><th>Severidade</th><th>Regra</th><th>Arquivo</th><th>Linha</th><th>Mensagem</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
