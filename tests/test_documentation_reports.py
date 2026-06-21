import tempfile
import textwrap
import unittest
from pathlib import Path

import quality_gate


class DocumentationQualityTest(unittest.TestCase):
    def test_markdown_documentation_is_checked_for_concision_and_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                textwrap.dedent(
                    """
                    ## Overview
                    line 1
                    line 2
                    line 3
                    ### Deep Detail
                    line 4
                    """
                ).strip(),
                encoding="utf-8",
            )

            config_path = root / "quality-gate.yml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    project:
                      name: "docs"
                      root: "."
                    scan:
                      include_extensions: []
                    thresholds:
                      max_lines_per_file: 100
                      warn_lines_per_file: 80
                      max_function_duplicates_allowed: 0
                      max_files_over_line_limit_allowed: 0
                      max_total_files_scanned: 100
                    coverage:
                      enabled: false
                    documentation:
                      enabled: true
                      include_extensions:
                        - ".md"
                      exclude_dirs:
                        - "quality-gate-report"
                      exclude_files: []
                      max_lines_per_doc: 5
                      max_section_lines: 2
                      max_heading_depth: 2
                      require_h1: true
                    rules:
                      file_lines:
                        enabled: false
                      duplicated_functions:
                        enabled: false
                      coverage:
                        enabled: false
                      documentation:
                        enabled: true
                    reports:
                      output_dir: "quality-gate-report"
                    """
                ).strip(),
                encoding="utf-8",
            )

            result = quality_gate.run_quality_gate(config_path, explicit_root=str(root))
            rules = {finding.rule for finding in result.findings}

            self.assertTrue(result.passed)
            self.assertLess(result.score, 100)
            self.assertEqual(result.summary["documentation"]["files_scanned"], 1)
            self.assertIn("documentation.max_lines", rules)
            self.assertIn("documentation.missing_h1", rules)
            self.assertIn("documentation.heading_depth", rules)
            self.assertIn("documentation.section_length", rules)


class ReportOutputTest(unittest.TestCase):
    def test_write_reports_generates_markdown_for_pull_request_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "quality-gate.yml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    project:
                      name: "report-project"
                      root: "."
                    reports:
                      output_dir: "quality-gate-report"
                      json_file: "quality-gate-report.json"
                      html_file: "quality-gate-report.html"
                      markdown_file: "quality-gate-report.md"
                    """
                ).strip(),
                encoding="utf-8",
            )
            result = quality_gate.GateResult(
                passed=True,
                score=100,
                summary={
                    "project": "report-project",
                    "profile": None,
                    "files_scanned": 2,
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

            json_path, html_path = quality_gate.write_reports(result, config_path, explicit_root=str(root))
            _, _, markdown_path = quality_gate.resolve_report_paths(config_path, explicit_root=str(root))
            markdown = markdown_path.read_text(encoding="utf-8")

            self.assertTrue(json_path.exists())
            self.assertTrue(html_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertIn("# Quality Gate Report", markdown)
            self.assertIn("## Documentação", markdown)
            self.assertIn("| Score | 100/100 |", markdown)


if __name__ == "__main__":
    unittest.main()
