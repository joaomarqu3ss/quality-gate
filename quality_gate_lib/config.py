import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    - ".rs"
    - ".dart"
    - ".c"
    - ".h"
    - ".cc"
    - ".cpp"
    - ".cxx"
    - ".hh"
    - ".hpp"
    - ".hxx"
  exclude_dirs:
    - ".git"
    - "node_modules"
    - "dist"
    - "build"
    - "coverage"
    - "target"
    - ".dart_tool"
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
  max_lines_per_file: 400
  max_function_duplicates_allowed: 0
  max_files_over_line_limit_allowed: 0
  min_coverage_percent: 80
  warn_lines_per_file: 250
  max_total_files_scanned: 5000

coverage:
  enabled: true
  paths:
    - "coverage/lcov.info"
    - "coverage/lcov-report/lcov.info"
    - "target/site/jacoco/jacoco.xml"
    - "coverage.xml"
    - "cobertura.xml"
    - "coverage/cobertura.xml"
    - "coverage/tarpaulin.xml"
    - "target/llvm-cov/lcov.info"
    - "coverage/coverage.info"
  fail_if_missing: false

documentation:
  enabled: true
  include_extensions:
    - ".md"
    - ".markdown"
  exclude_dirs:
    - ".git"
    - "node_modules"
    - "dist"
    - "build"
    - "coverage"
    - "target"
    - ".dart_tool"
    - ".angular"
    - ".idea"
    - ".vscode"
    - "__pycache__"
    - "quality-gate-report"
  exclude_files: []
  max_lines_per_doc: 300
  max_section_lines: 120
  max_heading_depth: 4
  require_h1: true

reports:
  output_dir: "quality-gate-report"
  json_file: "quality-gate-report.json"
  html_file: "quality-gate-report.html"
  markdown_file: "quality-gate-report.md"

llm_documentation:
  enabled: false
  provider: "openai-compatible"
  endpoint: "https://api.openai.com/v1/chat/completions"
  api_key_env: "OPENAI_API_KEY"
  model_env: "QUALITY_GATE_LLM_MODEL"
  model: ""
  output_file: "quality-gate-ai-review.md"
  timeout_seconds: 60
  temperature: 0.2
  max_output_tokens: 2000
  max_context_chars: 60000
  max_file_chars: 4000
  max_files: 80
  include_source_context: true
  include_documentation_context: true
  validate_output: true
  fail_if_unavailable: false
  fail_if_invalid: false

rules:
  duplicated_functions:
    enabled: true
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

  documentation:
    enabled: true
"""


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


def merge_unique_lists(base: List[Any], override: List[Any]) -> List[Any]:
    merged: List[Any] = []
    for item in [*base, *override]:
        if item not in merged:
            merged.append(item)
    return merged


def merge_config(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_config(merged[key], value)
        elif key in merged and isinstance(merged[key], list) and isinstance(value, list):
            merged[key] = merge_unique_lists(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_profile_path(config_dir: Path, profile_name: str) -> Path:
    profile_ref = Path(profile_name)
    if profile_ref.suffix in {".yml", ".yaml"} or len(profile_ref.parts) > 1:
        candidate = profile_ref if profile_ref.is_absolute() else config_dir / profile_ref
    else:
        candidate = config_dir / "profiles" / f"{profile_name}.yml"

    if candidate.exists():
        return candidate

    alternate_suffix = ".yaml" if candidate.suffix == ".yml" else ".yml"
    alternate = candidate.with_suffix(alternate_suffix)
    if alternate.exists():
        return alternate

    raise FileNotFoundError(f"Profile não encontrado: {candidate}")


def load_profile_config(config_dir: Path, profile_name: str, stack: Optional[List[str]] = None) -> Dict[str, Any]:
    stack = stack or []
    if profile_name in stack:
        chain = " -> ".join([*stack, profile_name])
        raise ValueError(f"Ciclo detectado em profiles: {chain}")

    profile_path = resolve_profile_path(config_dir, profile_name)
    profile_config = load_yaml_or_fallback(profile_path)
    parent = profile_config.get("extends")
    if not parent:
        profile_config.pop("extends", None)
        return profile_config

    parent_config = load_profile_config(config_dir, str(parent), [*stack, profile_name])
    profile_config = dict(profile_config)
    profile_config.pop("extends", None)
    return merge_config(parent_config, profile_config)


def load_quality_gate_config(config_path: Path, profile_name: Optional[str] = None) -> Dict[str, Any]:
    config = load_yaml_or_fallback(config_path)
    selected_profile = profile_name or config.get("profile") or deep_get(config, "project.profile")
    if not selected_profile:
        return config

    profile_config = load_profile_config(config_path.parent, str(selected_profile))
    return merge_config(profile_config, config)


def init_config(path: Path) -> None:
    if path.exists():
        print(f"Arquivo já existe: {path}")
        return
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    print(f"Configuração criada em: {path}")
