import re
from pathlib import Path
from typing import Any, Dict, List, Optional


_DECLARATION_PREFIX_RE = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*"
    r"(?:(?:external|static|abstract|operator)\s+)*"
    r"(?:(?P<return_type>[A-Za-z_$][\w$<>,? .\[\]]+)\s+)?"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*$",
    re.DOTALL,
)
_SCOPE_RE = re.compile(r"\b(class|mixin|extension|enum)\s+([A-Za-z_$][\w$]*)")
_CONTROL_WORDS = {"if", "for", "while", "switch", "catch", "return", "assert"}
_POST_PARAMS_RE = re.compile(r"^\s*(?:async\*?|sync\*?)?\s*(?:=>|\{)", re.MULTILINE)


def _normalize_params(params: str) -> str:
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


def _strip_comments_and_strings(content: str) -> str:
    chars = list(content)
    i = 0
    length = len(chars)

    while i < length:
        if content.startswith("//", i):
            end = content.find("\n", i + 2)
            end = length if end == -1 else end
            for j in range(i, end):
                chars[j] = " "
            i = end
            continue

        if content.startswith("/*", i):
            end = content.find("*/", i + 2)
            end = length - 2 if end == -1 else end
            for j in range(i, min(end + 2, length)):
                if chars[j] != "\n":
                    chars[j] = " "
            i = end + 2
            continue

        quote = chars[i]
        triple = content.startswith(quote * 3, i) if quote in {"'", '"'} else False
        if quote in {"'", '"'}:
            end = i + (3 if triple else 1)
            raw_start = i > 0 and chars[i - 1] == "r"
            for j in range(i, min(end, length)):
                chars[j] = " "
            i = end

            while i < length:
                if triple and content.startswith(quote * 3, i):
                    for j in range(i, min(i + 3, length)):
                        chars[j] = " "
                    i += 3
                    break
                if not triple and chars[i] == quote:
                    chars[i] = " "
                    i += 1
                    break
                if not raw_start and not triple and chars[i] == "\\":
                    chars[i] = " "
                    if i + 1 < length and chars[i + 1] != "\n":
                        chars[i + 1] = " "
                    i += 2
                    continue
                if chars[i] != "\n":
                    chars[i] = " "
                i += 1
            continue

        i += 1

    return "".join(chars)


def _find_matching_paren(content: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(content)):
        char = content[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _line_number(content: str, index: int) -> int:
    return content.count("\n", 0, index) + 1


def _nearest_statement_start(content: str, index: int) -> int:
    cursor = index - 1
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    while cursor >= 0:
        char = content[cursor]
        if char == ")":
            paren_depth += 1
        elif char == "(" and paren_depth > 0:
            paren_depth -= 1
        elif char == "]":
            bracket_depth += 1
        elif char == "[" and bracket_depth > 0:
            bracket_depth -= 1
        elif char == "}":
            brace_depth += 1
        elif char == "{" and brace_depth > 0:
            brace_depth -= 1

        if paren_depth == bracket_depth == brace_depth == 0 and char in "\n;{}":
            return cursor + 1
        cursor -= 1
    return 0


def _current_scope(scopes: List[Dict[str, Any]], brace_depth: int) -> Optional[Dict[str, Any]]:
    for scope in reversed(scopes):
        if brace_depth >= scope["body_depth"]:
            return scope
    return None


def _maybe_function_at(
    content: str,
    open_index: int,
    brace_depth: int,
    scopes: List[Dict[str, Any]],
    rel_file: str,
) -> Optional[Dict[str, Any]]:
    close_index = _find_matching_paren(content, open_index)
    if close_index == -1:
        return None

    if not _POST_PARAMS_RE.match(content[close_index + 1 : close_index + 80]):
        return None

    statement_start = _nearest_statement_start(content, open_index)
    prefix = content[statement_start:open_index].strip()
    if not prefix or "=" in prefix:
        return None
    if prefix.startswith(("factory ", "typedef ", "return ")):
        return None

    declaration = _DECLARATION_PREFIX_RE.match(prefix)
    if not declaration:
        return None

    name = declaration.group("name")
    return_type = (declaration.group("return_type") or "").strip()
    if name in _CONTROL_WORDS:
        return None

    scope = _current_scope(scopes, brace_depth)
    if scope is None and brace_depth != 0:
        return None
    if scope is not None and brace_depth != scope["body_depth"]:
        return None
    if scope is not None and name == scope["name"]:
        return None
    if scope is None and not return_type:
        return None

    params = _normalize_params(content[open_index + 1 : close_index])
    signature = f"{name}({params})"
    if scope is None:
        dedupe_key = signature
    else:
        dedupe_key = f'{scope["kind"]}:{scope["name"]}::{signature}'

    return {
        "name": name,
        "signature": signature,
        "dedupe_key": dedupe_key,
        "pattern": "dart_function",
        "file": rel_file,
        "line": _line_number(content, statement_start),
    }


def find_dart_functions(file_path: Path, root: Path) -> List[Dict[str, Any]]:
    try:
        original = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    content = _strip_comments_and_strings(original)
    rel_file = str(file_path.relative_to(root))
    functions: List[Dict[str, Any]] = []
    seen_matches = set()
    scopes: List[Dict[str, Any]] = []
    pending_scope: Optional[Dict[str, Any]] = None
    brace_depth = 0
    i = 0

    while i < len(content):
        scope_match = _SCOPE_RE.match(content, i)
        if scope_match:
            pending_scope = {"kind": scope_match.group(1), "name": scope_match.group(2)}
            i = scope_match.end()
            continue

        char = content[i]
        if char == "(":
            function = _maybe_function_at(content, i, brace_depth, scopes, rel_file)
            if function:
                match_key = (function["dedupe_key"], function["line"])
                if match_key not in seen_matches:
                    seen_matches.add(match_key)
                    functions.append(function)
                close_index = _find_matching_paren(content, i)
                if close_index != -1:
                    i = close_index + 1
                    continue
        elif char == "{":
            brace_depth += 1
            if pending_scope is not None:
                pending_scope["body_depth"] = brace_depth
                scopes.append(pending_scope)
                pending_scope = None
        elif char == "}":
            while scopes and brace_depth < scopes[-1]["body_depth"]:
                scopes.pop()
            brace_depth = max(0, brace_depth - 1)
            while scopes and brace_depth < scopes[-1]["body_depth"]:
                scopes.pop()
            pending_scope = None
        elif char == ";":
            pending_scope = None

        i += 1

    return functions
