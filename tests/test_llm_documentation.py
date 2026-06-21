import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import quality_gate


class LlmDocumentationTest(unittest.TestCase):
    def test_llm_documentation_is_generated_and_validated_with_fake_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Existing Docs\n\nContexto atual.\n", encoding="utf-8")
            (root / "app.py").write_text("def handler():\n    return 'ok'\n", encoding="utf-8")
            config_path = root / "quality-gate.yml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    project:
                      name: "llm-docs"
                      root: "."
                    scan:
                      include_extensions:
                        - ".py"
                    documentation:
                      enabled: true
                      include_extensions:
                        - ".md"
                      exclude_dirs:
                        - "quality-gate-report"
                      exclude_files: []
                      max_lines_per_doc: 40
                      max_section_lines: 20
                      max_heading_depth: 3
                      require_h1: true
                    reports:
                      output_dir: "quality-gate-report"
                      markdown_file: "quality-gate-report.md"
                    llm_documentation:
                      enabled: true
                      endpoint: "https://example.invalid/v1/chat/completions"
                      api_key_env: "TEST_LLM_API_KEY"
                      model: "fake-review-model"
                      output_file: "quality-gate-ai-review.md"
                      max_files: 5
                      max_file_chars: 200
                      max_context_chars: 8000
                      validate_output: true
                    rules:
                      file_lines:
                        enabled: false
                      duplicated_functions:
                        enabled: false
                      coverage:
                        enabled: false
                      documentation:
                        enabled: true
                    coverage:
                      enabled: false
                    """
                ).strip(),
                encoding="utf-8",
            )
            result = quality_gate.GateResult(
                passed=True,
                score=100,
                summary={
                    "project": "llm-docs",
                    "profile": None,
                    "files_scanned": 1,
                    "total_functions_detected": 1,
                    "errors": 0,
                    "warnings": 0,
                    "coverage": {"enabled": False, "coverage_percent": None, "source": None, "missing": False},
                    "documentation": {
                        "enabled": True,
                        "files_scanned": 1,
                        "docs_over_line_limit": 0,
                        "sections_over_limit": 0,
                        "docs_missing_h1": 0,
                        "docs_with_deep_headings": 0,
                    },
                },
                findings=[],
            )
            quality_gate.write_reports(result, config_path, explicit_root=str(root))

            def fake_http_post(url, headers, payload, timeout):
                self.assertEqual(url, "https://example.invalid/v1/chat/completions")
                self.assertEqual(headers["Authorization"], "Bearer test-secret")
                self.assertEqual(payload["model"], "fake-review-model")
                user_context = payload["messages"][1]["content"]
                self.assertIn("README.md", user_context)
                self.assertIn("app.py", user_context)
                return {"choices": [{"message": {"content": "# Quality Gate AI Review\n\nGate aprovado."}}]}

            with patch.dict(os.environ, {"TEST_LLM_API_KEY": "test-secret"}):
                llm_result = quality_gate.run_llm_documentation(
                    config_path,
                    result,
                    explicit_root=str(root),
                    http_post=fake_http_post,
                )

            output_path = root / "quality-gate-report" / "quality-gate-ai-review.md"
            self.assertFalse(llm_result["skipped"])
            self.assertTrue(llm_result["valid"])
            self.assertTrue(output_path.exists())
            self.assertIn("# Quality Gate AI Review", output_path.read_text(encoding="utf-8"))

    def test_llm_documentation_skips_without_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "quality-gate.yml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    project:
                      name: "missing-key"
                      root: "."
                    reports:
                      output_dir: "quality-gate-report"
                    llm_documentation:
                      enabled: true
                      api_key_env: "MISSING_TEST_LLM_API_KEY"
                      model: "fake-review-model"
                    """
                ).strip(),
                encoding="utf-8",
            )
            result = quality_gate.GateResult(
                passed=True,
                score=100,
                summary={
                    "project": "missing-key",
                    "profile": None,
                    "files_scanned": 0,
                    "total_functions_detected": 0,
                    "errors": 0,
                    "warnings": 0,
                    "coverage": {"enabled": False, "coverage_percent": None, "source": None, "missing": False},
                },
                findings=[],
            )

            with patch.dict(os.environ, {}, clear=True):
                llm_result = quality_gate.run_llm_documentation(config_path, result, explicit_root=str(root))

            self.assertTrue(llm_result["skipped"])
            self.assertIn("MISSING_TEST_LLM_API_KEY", llm_result["error"])


if __name__ == "__main__":
    unittest.main()
