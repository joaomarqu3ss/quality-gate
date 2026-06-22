import tempfile
import textwrap
import unittest
from pathlib import Path

import quality_gate


class DartScannerTest(unittest.TestCase):
    def test_flutter_widget_calls_and_closures_are_not_detected_as_functions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dart_file = root / "ponto_actions.dart"
            dart_file.write_text(
                textwrap.dedent(
                    """
                    class PontoActions extends StatefulWidget {
                      const PontoActions({super.key});

                      @override
                      State<PontoActions> createState() => _PontoActionsState();
                    }

                    class _PontoActionsState extends State<PontoActions> {
                      void clear() {
                        setState(() {
                          selected = null;
                        });
                      }

                      Future<void> logout() async {
                        return;
                      }

                      @override
                      Widget build(BuildContext context) {
                        return GestureDetector(
                          onTap: () {
                            clear();
                          },
                          child: _HeaderIconButton(
                            icon: Icons.notifications_outlined,
                            tooltip: 'Notificações',
                            onTap: () {},
                          ),
                        );
                      }
                    }
                    """
                ).strip(),
                encoding="utf-8",
            )

            functions = quality_gate.find_functions(dart_file, root)
            signatures = {fn["signature"] for fn in functions}

            self.assertIn("clear()", signatures)
            self.assertIn("logout()", signatures)
            self.assertIn("build(BuildContext context)", signatures)
            self.assertNotIn("PontoActions(super.key)", signatures)
            self.assertNotIn("GestureDetector(onTap: ()", signatures)
            self.assertNotIn("_HeaderIconButton(icon: Icons.notifications_outlined,tooltip:)", signatures)
            self.assertNotIn("setState(()", signatures)

    def test_methods_in_different_classes_do_not_duplicate_by_signature_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lib = root / "lib"
            lib.mkdir()

            (lib / "storage.dart").write_text(
                textwrap.dedent(
                    """
                    class SecureStorage {
                      Future<void> clear() async {}
                    }
                    """
                ).strip(),
                encoding="utf-8",
            )
            (lib / "queue.dart").write_text(
                textwrap.dedent(
                    """
                    class OfflineQueue {
                      Future<void> clear() async {}
                    }
                    """
                ).strip(),
                encoding="utf-8",
            )
            (lib / "parse_a.dart").write_text(
                "Map<String, dynamic> resolvePayload(Map<String, dynamic> json) => json;\n",
                encoding="utf-8",
            )
            (lib / "parse_b.dart").write_text(
                "Map<String, dynamic> resolvePayload(Map<String, dynamic> json) => json;\n",
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
                      exclude_dirs: []
                      exclude_files: []
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

            self.assertEqual(len(duplicate_messages), 1)
            self.assertIn("resolvePayload(Map<String,dynamic> json)", duplicate_messages[0])
            self.assertFalse(any("clear()" in msg for msg in duplicate_messages))

            clear_keys = {
                fn["dedupe_key"]
                for file_path in (lib / "storage.dart", lib / "queue.dart")
                for fn in quality_gate.find_functions(file_path, root)
                if fn["signature"] == "clear()"
            }
            self.assertEqual(
                clear_keys,
                {
                    "class:SecureStorage::clear()",
                    "class:OfflineQueue::clear()",
                },
            )

    def test_flutter_profile_ignores_main_entrypoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lib = root / "lib"
            tests = root / "test"
            lib.mkdir()
            tests.mkdir()
            (lib / "main.dart").write_text("void main() {}\n", encoding="utf-8")
            (tests / "widget_test.dart").write_text("void main() {}\n", encoding="utf-8")

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
                      exclude_dirs: []
                      exclude_files: []
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

            repo_root = Path(__file__).resolve().parents[1]
            profile = repo_root / "profiles" / "flutter.yml"
            result = quality_gate.run_quality_gate(
                config_path,
                explicit_root=str(root),
                profile_name=str(profile),
            )
            duplicate_messages = [
                finding.message
                for finding in result.findings
                if finding.rule == "function.duplicate_signature"
            ]

            self.assertEqual(result.summary["total_functions_detected"], 2)
            self.assertEqual(duplicate_messages, [])


if __name__ == "__main__":
    unittest.main()
