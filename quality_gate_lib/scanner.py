import fnmatch
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from quality_gate_lib.config import deep_get


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
    (
        "rust_function",
        re.compile(
            r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:(?:async|unsafe|const)\s+)*fn\s+([A-Za-z_][\w]*)\s*(?:<[^>\n]+>\s*)?\(([^)]*)\)",
            re.MULTILINE,
        ),
    ),
    (
        "dart_function",
        re.compile(
            r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*(?:(?:external|static|abstract|factory)\s+)*(?:[A-Za-z_$][\w$<>,? .\[\]]+\s+)?([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?:async\*?|sync\*?)?\s*(?:=>|\{)",
            re.MULTILINE,
        ),
    ),
    (
        "c_cpp_function",
        re.compile(
            r"^\s*(?!(?:if|for|while|switch|catch|return)\b)(?:[A-Za-z_][\w:<>,\s\*\&\[\]]+\s+)+([A-Za-z_][\w]*)\s*\(([^;{}]*)\)\s*(?:const\s*)?(?:noexcept\s*)?(?:->\s*[^{]+)?\{",
            re.MULTILINE,
        ),
    ),
]

PATTERN_EXTENSIONS = {
    "js_ts_function": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"},
    "js_ts_arrow_const": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"},
    "js_ts_method": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"},
    "python_def": {".py", ".pyw"},
    "java_method": {".java"},
    "go_func": {".go"},
    "csharp_method": {".cs", ".csx"},
    "rust_function": {".rs"},
    "dart_function": {".dart"},
    "c_cpp_function": {".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx"},
}


def normalize_params(params: str) -> str:
    params = re.sub(r"\s+", " ", params.strip())
    if not params:
        return ""
    parts = [p.strip() for p in params.split(",") if p.strip()]
    normalized = []
    for p in parts:
        p = p.split("=")[0].strip()
        p = re.sub(r"\b(final|readonly|public|private|protected)\b", "", p).strip()
        normalized.append(p)
    return ",".join(normalized)


def find_functions(file_path: Path, root: Path) -> List[Dict[str, Any]]:
    if file_path.suffix.lower() == ".dart":
        from quality_gate_lib.dart_scanner import find_dart_functions

        return find_dart_functions(file_path, root)

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    functions: List[Dict[str, Any]] = []
    seen_matches = set()
    suffix = file_path.suffix.lower()
    for pattern_name, pattern in FUNCTION_PATTERNS:
        allowed_extensions = PATTERN_EXTENSIONS.get(pattern_name)
        if allowed_extensions and suffix not in allowed_extensions:
            continue

        for match in pattern.finditer(content):
            name = match.group(1)
            params = normalize_params(match.group(2) if match.lastindex and match.lastindex >= 2 else "")
            line = content.count("\n", 0, match.start()) + 1

            if name in {"if", "for", "while", "switch", "catch", "return"}:
                continue

            match_key = (name, params, line)
            if match_key in seen_matches:
                continue
            seen_matches.add(match_key)

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
