"""Native text dialog, persistence, export, and cancellation regression."""
import tempfile
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from desktop.editor import ScreenshotEditor
from desktop.retention import CacheRetention
from desktop.text_annotation_dialog import (
    TextAnnotationDialog, normalized_color, font_size_from,
)


class TextDialogTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.parent = tk.Toplevel(self.root)
        self.parent.geometry("500x350+150+120")
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def test_actual_dialog_controls_size_swatches_picker_and_confirm(self):
        dialog = TextAnnotationDialog(self.parent, initial_color="#ff2d2d", initial_size=22)
        self.root.update()
        self.assertEqual(dialog.size_var.get(), "22")
        self.assertEqual(len(dialog.swatch_buttons), 6)
        self.assertTrue(dialog.size_box.winfo_ismapped())
        self.assertTrue(dialog.entry.winfo_ismapped())
        dialog.entry.insert(0, "你好 Charlie")
        dialog.size_var.set("36")
        dialog.set_color("#3b82f6")
        dialog.update_preview()
        self.assertEqual(dialog.preview.cget("fg"), "#3b82f6")
        with patch("desktop.text_annotation_dialog.colorchooser.askcolor",
                   return_value=((1, 2, 3), "#010203")):
            dialog.choose_color()
        self.assertEqual(dialog.color, "#010203")
        self.assertEqual(dialog.confirm(), "break")
        self.assertEqual(dialog.result, ("你好 Charlie", 36, "#010203"))

    def test_cancel_invalid_input_and_bounds(self):
        dialog = TextAnnotationDialog(self.parent)
        dialog.entry.insert(0, "文")
        dialog.size_var.set("500")
        dialog.confirm()
        self.assertIsNone(dialog.result)
        self.assertTrue(dialog.winfo_exists())
        dialog.cancel()
        self.assertIsNone(dialog.result)
        self.assertEqual(font_size_from("24"), 24)
        self.assertEqual(font_size_from("500"), 22)
        self.assertEqual(normalized_color("#GGGGGG"), "#ff2d2d")

    def test_confirm_empty_text_keeps_dialog_open(self):
        dialog = TextAnnotationDialog(self.parent)
        dialog.confirm()
        self.assertIsNone(dialog.result)
        self.assertTrue(dialog.winfo_exists())
        dialog.cancel()
    def test_editor_reopens_with_persisted_text_size_and_color(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = CacheRetention(tmp)
            editor = ScreenshotEditor(
                self.root, Image.new("RGB", (520, 200), "white"),
                lambda *_: None, lambda: None, settings=settings,
            )
            editor.set_tool("text")
            self.root.update()
            with patch("desktop.editor.TextAnnotationDialog.ask",
                       return_value=("你好世界", 38, "#2563eb")) as ask:
                editor.press(SimpleNamespace(x=50, y=55))
            ask.assert_called_once()
            self.assertEqual(editor.annotations[-1]["font_size"], 38)
            self.assertEqual(editor.annotations[-1]["color"], "#2563eb")
            self.assertEqual(editor.annotations[-1]["text"], "你好世界")
            count = len(editor.undo_stack)
            with patch("desktop.editor.TextAnnotationDialog.ask", return_value=None):
                editor.press(SimpleNamespace(x=180, y=80))
            self.assertEqual(len(editor.annotations), 1)
            self.assertEqual(len(editor.undo_stack), count)
            editor.cancel()
            reopened = ScreenshotEditor(
                self.root, Image.new("RGB", (320, 140), "white"),
                lambda *_: None, lambda: None, settings=CacheRetention(tmp),
            )
            self.assertEqual(reopened.text_size, 38)
            self.assertEqual(reopened.text_color, "#2563eb")
            self.assertEqual(reopened.tool, "text")
            reopened.cancel()
    def test_export_text_font_size_and_color_independent_of_stroke(self):
        editor = ScreenshotEditor.__new__(ScreenshotEditor)
        editor.base = Image.new("RGB", (460, 190), "#ffffff")
        editor.annotations = [
            {"type": "text", "p": (20, 26), "text": "字", "color": "#ff0000",
             "font_size": 16, "width": 6},
            {"type": "text", "p": (210, 26), "text": "字", "color": "#0000ff",
             "font_size": 44, "width": 6},
        ]
        image = editor._flatten()
        rgb = image.convert("RGB")
        colors = rgb.getcolors(460*190)
        red = sum(n for n, c in colors if c[0] > 150 and c[1] < 120 and c[2] < 120)
        blue = sum(n for n, c in colors if c[2] > 150 and c[0] < 120 and c[1] < 120)
        self.assertGreater(red, 10)
        self.assertGreater(blue, red * 2)
        self.assertEqual(editor._text_font_size({"width": 4}), 18)
        rgb.close()
        image.close()
        editor.base.close()


if __name__ == "__main__":
    unittest.main()
