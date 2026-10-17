"""Run real Tk modal tests in an isolated interpreter.

The full PP-OCRv5 test initializes ONNX worker threads. Tk objects finalized
from those threads can crash the whole test process during interpreter exit.
Do not weaken assertions: the child must execute all 5 actual GUI tests and
exit cleanly before this wrapper passes.
"""
import subprocess
import sys
import unittest
from pathlib import Path


class OwnedTkProcessTests(unittest.TestCase):
    def test_real_modal_controls_persistence_and_export(self):
        repo = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "-m", "unittest",
             "desktop.tests.editor_text_dialog_cases", "-v"],
            cwd=repo,
            capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 5 tests", result.stderr)
        self.assertIn("OK", result.stderr)
