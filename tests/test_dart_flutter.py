import tempfile
import textwrap
import unittest
from pathlib import Path

import quality_gate


class DartLanguageDetectionTest(unittest.TestCase):
    def test_dart_functions_and_methods_are_detected_and_duplicate_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lib = root / "lib"
            lib.mkdir()

            (lib / "alpha.dart").write_text(
                textwrap.dedent(
                    """
                    int checksum(int value) {
                      return value;
                    }

                    class AlphaWidget {
                      @override
                      Widget build(BuildContext context) {
                        return const Text('Alpha');
                      }
                    }
                    """
                ).strip(),
                encoding="utf-8",
            )
            (lib / "beta.dart").write_text(
                textwrap.dedent(
                    """
                    Future<int> checksum(int value) async {
                      return value + 1;
                    }

                    class BetaWidget {
                      @override
                      Widget build(BuildContext context) => const Text('Beta');
                    }
                    """
                ).strip(),
                encoding="utf-8",
            )
            (lib / "alpha.g.dart").write_text(
                "int generatedHelper() => 1;\n",
                encoding="utf-8",
            )

            config_path = root / "quality-gate.yml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    project:
                      name: "flutter-app"
                      root: "."
                    scan:
                      include_extensions:
                        - ".dart"
                      exclude_dirs:
                        - ".dart_tool"
                      exclude_files:
                        - "*.g.dart"
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
                        ignore_names:
                          - "build"
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

            self.assertEqual(result.summary["files_scanned"], 2)
            self.assertEqual(result.summary["total_functions_detected"], 4)
            self.assertTrue(any("checksum(int value)" in msg for msg in duplicate_messages))
            self.assertFalse(any("build(BuildContext context)" in msg for msg in duplicate_messages))
            self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
