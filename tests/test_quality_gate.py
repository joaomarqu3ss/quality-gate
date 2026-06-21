import tempfile
import textwrap
import unittest
import io
from pathlib import Path
from unittest.mock import patch

import quality_gate


class QualityGateProfilesTest(unittest.TestCase):
    def test_profile_config_merges_lists_with_project_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles = root / "profiles"
            profiles.mkdir()

            (profiles / "rust.yml").write_text(
                textwrap.dedent(
                    """
                    scan:
                      include_extensions:
                        - ".rs"
                      exclude_dirs:
                        - "target"
                    coverage:
                      paths:
                        - "coverage/tarpaulin.xml"
                    """
                ).strip(),
                encoding="utf-8",
            )
            config_path = root / "quality-gate.yml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    project:
                      name: "profile-merge"
                      root: "."
                    scan:
                      include_extensions:
                        - ".py"
                      exclude_dirs:
                        - "__pycache__"
                    coverage:
                      paths:
                        - "coverage.xml"
                    """
                ).strip(),
                encoding="utf-8",
            )

            config = quality_gate.load_quality_gate_config(config_path, profile_name="rust")

            self.assertEqual(config["project"]["name"], "profile-merge")
            self.assertEqual(config["scan"]["include_extensions"], [".rs", ".py"])
            self.assertEqual(config["scan"]["exclude_dirs"], ["target", "__pycache__"])
            self.assertEqual(config["coverage"]["paths"], ["coverage/tarpaulin.xml", "coverage.xml"])

    def test_flutter_profile_scans_dart_and_uses_lcov_coverage(self):
        repo_root = Path(__file__).resolve().parents[1]
        config_path = repo_root / "quality-gate.yml"

        config = quality_gate.load_quality_gate_config(config_path, profile_name="flutter")

        self.assertIn(".dart", config["scan"]["include_extensions"])
        self.assertIn(".dart_tool", config["scan"]["exclude_dirs"])
        self.assertIn("*.freezed.dart", config["scan"]["exclude_files"])
        self.assertIn("coverage/lcov.info", config["coverage"]["paths"])
        self.assertIn("build", config["rules"]["duplicated_functions"]["ignore_names"])


class LowLevelLanguageDetectionTest(unittest.TestCase):
    def test_language_specific_patterns_do_not_parse_python_string_snippets_as_c(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "snippet.py"
            script.write_text(
                textwrap.dedent(
                    '''
                    C_SNIPPET = """
                    int encode(int value) {
                        return value;
                    }
                    """

                    def real_function(value):
                        return value
                    '''
                ).strip(),
                encoding="utf-8",
            )

            functions = quality_gate.find_functions(script, root)

            self.assertEqual([fn["signature"] for fn in functions], ["real_function(value)"])

    def test_rust_and_c_functions_are_detected_and_duplicate_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            src.mkdir()

            (src / "alpha.rs").write_text(
                "pub fn checksum(value: i32) -> i32 {\n    value\n}\n",
                encoding="utf-8",
            )
            (src / "beta.rs").write_text(
                "fn checksum(value: i32) -> i32 {\n    value + 1\n}\n",
                encoding="utf-8",
            )
            (src / "alpha.c").write_text(
                "int encode(int value) {\n    return value;\n}\n",
                encoding="utf-8",
            )
            (src / "beta.c").write_text(
                "int encode(int value) {\n    return value + 1;\n}\n",
                encoding="utf-8",
            )

            config_path = root / "quality-gate.yml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    project:
                      name: "low-level"
                      root: "."
                    scan:
                      include_extensions:
                        - ".rs"
                        - ".c"
                    thresholds:
                      max_lines_per_file: 100
                      warn_lines_per_file: 80
                      max_function_duplicates_allowed: 0
                      max_files_over_line_limit_allowed: 0
                      max_total_files_scanned: 100
                    coverage:
                      enabled: false
                    rules:
                      file_lines:
                        enabled: true
                      duplicated_functions:
                        enabled: true
                        ignore_names: []
                      coverage:
                        enabled: false
                    reports:
                      output_dir: "quality-gate-report"
                    """
                ).strip(),
                encoding="utf-8",
            )

            result = quality_gate.run_quality_gate(config_path, explicit_root=str(root))

            duplicate_messages = [
                finding.message
                for finding in result.findings
                if finding.rule == "function.duplicate_signature"
            ]
            self.assertEqual(result.summary["total_functions_detected"], 4)
            self.assertTrue(any("checksum(value: i32)" in msg for msg in duplicate_messages))
            self.assertTrue(any("encode(int value)" in msg for msg in duplicate_messages))
            self.assertFalse(result.passed)


class ConsoleOutputTest(unittest.TestCase):
    def test_console_summary_is_ascii_safe_for_cp1252_terminals(self):
        result = quality_gate.GateResult(
            passed=False,
            score=85,
            summary={
                "files_scanned": 1,
                "total_functions_detected": 0,
                "errors": 1,
                "warnings": 0,
                "coverage": {"enabled": False, "coverage_percent": None, "source": None, "missing": False},
            },
            findings=[],
        )
        output = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")

        with patch("sys.stdout", output):
            quality_gate.print_console_summary(result, Path("report.json"), Path("report.html"))

        output.seek(0)
        self.assertIn("[FAIL] QUALITY GATE: FALHOU", output.read())


if __name__ == "__main__":
    unittest.main()
