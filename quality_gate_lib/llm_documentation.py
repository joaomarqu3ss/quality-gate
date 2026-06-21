import dataclasses
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from quality_gate_lib.config import deep_get, load_quality_gate_config
from quality_gate_lib.documentation import analyze_documentation_file, iter_documentation_files
from quality_gate_lib.models import GateResult
from quality_gate_lib.reports import resolve_report_paths
from quality_gate_lib.scanner import iter_source_files


HttpPost = Callable[[str, Dict[str, str], Dict[str, Any], int], Dict[str, Any]]


def llm_documentation_enabled(config: Dict[str, Any]) -> bool:
    return bool(deep_get(config, "llm_documentation.enabled", False))


def resolve_llm_documentation_path(root: Path, config: Dict[str, Any]) -> Path:
    output_dir = root / deep_get(config, "reports.output_dir", "quality-gate-report")
    return output_dir / deep_get(config, "llm_documentation.output_file", "quality-gate-ai-review.md")


def trim_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[conteudo truncado pelo quality gate]\n"


def collect_file_context(root: Path, config: Dict[str, Any], max_files: int, max_file_chars: int) -> List[str]:
    include_source = bool(deep_get(config, "llm_documentation.include_source_context", True))
    include_docs = bool(deep_get(config, "llm_documentation.include_documentation_context", True))
    files: List[Path] = []

    if include_docs:
        files.extend(iter_documentation_files(root, config))
    if include_source:
        files.extend(iter_source_files(root, config))

    snippets: List[str] = []
    seen = set()
    for file_path in files:
        if file_path in seen:
            continue
        seen.add(file_path)
        if len(snippets) >= max_files:
            break
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = file_path.relative_to(root)
        snippets.append(f"### {rel}\n\n```text\n{trim_text(content, max_file_chars)}\n```")

    return snippets


def build_llm_documentation_context(
    root: Path,
    config: Dict[str, Any],
    result: GateResult,
    markdown_report: str,
) -> str:
    max_context_chars = int(deep_get(config, "llm_documentation.max_context_chars", 60000))
    max_files = int(deep_get(config, "llm_documentation.max_files", 80))
    max_file_chars = int(deep_get(config, "llm_documentation.max_file_chars", 4000))
    findings = [dataclasses.asdict(finding) for finding in result.findings[:100]]
    context = [
        "# Contexto para documentação pós-review",
        "",
        "## Resultado do quality gate",
        "",
        json.dumps(
            {
                "passed": result.passed,
                "score": result.score,
                "summary": result.summary,
                "findings": findings,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "",
        "## Relatório Markdown gerado pelo gate",
        "",
        markdown_report,
        "",
        "## Arquivos de contexto",
        "",
        *collect_file_context(root, config, max_files=max_files, max_file_chars=max_file_chars),
    ]
    return trim_text("\n".join(context), max_context_chars)


def build_llm_payload(config: Dict[str, Any], context: str) -> Dict[str, Any]:
    model = os.environ.get(str(deep_get(config, "llm_documentation.model_env", "QUALITY_GATE_LLM_MODEL"))) or deep_get(
        config,
        "llm_documentation.model",
        "",
    )
    system_prompt = deep_get(
        config,
        "llm_documentation.system_prompt",
        (
            "Voce e um revisor tecnico. Gere uma documentacao pos-review em Markdown, "
            "concisa, verificavel e adequada para comentario de Pull Request. "
            "Inclua: resumo executivo, decisao do gate, riscos, findings, acoes recomendadas "
            "e links/nomes de artefatos quando existirem. Nao invente fatos fora do contexto."
        ),
    )
    return {
        "model": model,
        "temperature": float(deep_get(config, "llm_documentation.temperature", 0.2)),
        "max_tokens": int(deep_get(config, "llm_documentation.max_output_tokens", 2000)),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ],
    }


def default_http_post(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Erro HTTP do provedor LLM: {exc.code} {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha ao chamar provedor LLM: {exc.reason}") from exc


def extract_llm_content(response: Dict[str, Any]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()

    output_text = response.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()

    raise RuntimeError("Resposta do provedor LLM não contém conteúdo em formato esperado.")


def call_llm(config: Dict[str, Any], context: str, http_post: Optional[HttpPost] = None) -> str:
    provider = deep_get(config, "llm_documentation.provider", "openai-compatible")
    if provider != "openai-compatible":
        raise RuntimeError(f"Provider LLM não suportado: {provider}")

    payload = build_llm_payload(config, context)
    if not payload.get("model"):
        raise RuntimeError("Modelo LLM não configurado. Defina llm_documentation.model ou QUALITY_GATE_LLM_MODEL.")

    api_key_env = str(deep_get(config, "llm_documentation.api_key_env", "OPENAI_API_KEY"))
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"API key não encontrada. Configure a variável de ambiente {api_key_env}.")

    endpoint = str(deep_get(config, "llm_documentation.endpoint", "https://api.openai.com/v1/chat/completions"))
    timeout = int(deep_get(config, "llm_documentation.timeout_seconds", 60))
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    transport = http_post or default_http_post
    return extract_llm_content(transport(endpoint, headers, payload, timeout))


def validate_generated_documentation(root: Path, config: Dict[str, Any], output_path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    summary, findings = analyze_documentation_file(output_path, root, config)
    return summary, [dataclasses.asdict(finding) for finding in findings]


def run_llm_documentation(
    config_path: Path,
    result: GateResult,
    explicit_root: Optional[str] = None,
    profile_name: Optional[str] = None,
    http_post: Optional[HttpPost] = None,
) -> Dict[str, Any]:
    config = load_quality_gate_config(config_path, profile_name=profile_name)
    if not llm_documentation_enabled(config):
        return {"enabled": False, "skipped": True}

    root = Path(explicit_root or deep_get(config, "project.root", ".")).resolve()
    _, _, markdown_path = resolve_report_paths(config_path, explicit_root=explicit_root, profile_name=profile_name)
    markdown_report = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
    output_path = resolve_llm_documentation_path(root, config)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        context = build_llm_documentation_context(root, config, result, markdown_report)
        content = call_llm(config, context, http_post=http_post)
    except Exception as exc:
        return {
            "enabled": True,
            "skipped": True,
            "error": str(exc),
            "output": str(output_path),
            "fail_if_unavailable": bool(deep_get(config, "llm_documentation.fail_if_unavailable", False)),
        }

    output_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    response: Dict[str, Any] = {
        "enabled": True,
        "skipped": False,
        "output": str(output_path),
        "fail_if_invalid": bool(deep_get(config, "llm_documentation.fail_if_invalid", False)),
    }

    if bool(deep_get(config, "llm_documentation.validate_output", True)):
        validation, findings = validate_generated_documentation(root, config, output_path)
        response["validation"] = validation
        response["validation_findings"] = findings
        response["valid"] = not findings

    return response
