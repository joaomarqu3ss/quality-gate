# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python 3.10+ quality gate CLI. The root `quality_gate.py` is a compatibility entrypoint that re-exports the package API and calls `quality_gate_lib.cli.main()`. Core implementation lives in `quality_gate_lib/`: `config.py` loads and merges YAML config, `engine.py` runs rules, `scanner.py` finds files and functions, `coverage.py` parses coverage files, and `reports.py` writes output. Stack defaults live in `profiles/*.yml`. Tests are in `tests/`, currently centered on `tests/test_quality_gate.py`. Generated reports are written to `quality-gate-report/` and should not be treated as source.

## Build, Test, and Development Commands

- `pip install pyyaml`: install the only runtime dependency documented by the project.
- `python -m unittest discover`: run the test suite.
- `python quality_gate.py --config quality-gate.yml --root .`: run the gate against this repository.
- `python quality_gate.py --config quality-gate.yml --profile rust --root .`: run with a stack profile; replace `rust` with `node`, `python`, `java-spring`, `angular`, `csharp-dotnet`, or `c-cpp`.
- `python quality_gate.py --init-config`: create a default `quality-gate.yml` when starting a new project.

## Coding Style & Naming Conventions

Use 4-space indentation, standard-library imports before local imports, and clear snake_case names for modules, functions, and variables. Keep dataclasses in `models.py` small and serializable. Prefer `pathlib.Path` for filesystem work and typed function signatures for shared library functions. Preserve the current compatibility surface in `quality_gate.py` when moving or renaming internals, because tests and users import from it directly.

## Testing Guidelines

Tests use Python `unittest`. Name files `test_*.py`, test classes after the behavior under test, and methods as `test_<expected_behavior>`. Use `tempfile.TemporaryDirectory()` for filesystem scenarios and write fixture files with explicit UTF-8 encoding. Add tests for config merge behavior, profile resolution, scanner edge cases, coverage parsing, and CLI/report behavior when those areas change.

## Commit & Pull Request Guidelines

Recent history uses short, imperative commits, with optional Conventional Commit prefixes such as `feat:`. Keep messages focused, for example `feat: add python profile coverage paths` or `fix: avoid duplicate profile list entries`. Pull requests should include a concise problem summary, the implementation approach, test commands run, and any changes to `quality-gate.yml` or `profiles/`. Include report screenshots only when HTML output changes.

## Security & Configuration Tips

Do not commit generated `quality-gate-report/` output or local coverage artifacts unless explicitly needed as fixtures. Keep profile YAML generic and avoid project secrets in `quality-gate.yml`. When adding scan paths, update `exclude_dirs` and `exclude_files` to avoid generated dependencies such as `node_modules`, `target`, `dist`, and `coverage`.
