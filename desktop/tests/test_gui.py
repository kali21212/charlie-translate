"""Owned Tk surfaces only; no input is sent to other applications."""
import tempfile
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
import unittest
from PIL import Image
from desktop.editor import ScreenshotEditor
from desktop.floating import FloatingButton


class CompactGuiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_small_capture_keeps_its_size_and_closes_after_copy(self):
        completed = []
        editor = ScreenshotEditor(self.root, Image.new("RGB", (420, 90), "white"), lambda image, action: completed.append((image, action)), lambda: None, position=(120, 150))
        self.root.update()
        self.assertEqual((editor.window.winfo_width(), editor.window.winfo_height()), (426, 96))
        self.assertLess(editor.toolbar.winfo_height(), 90)
        self.assertEqual(editor._point(SimpleNamespace(x=3,y=3)), (0,0))
        self.assertIsNone(editor._toolbar_hit(SimpleNamespace(x=editor.button_positions[0]+33,y=20)))
        self.assertEqual(editor._toolbar_hit(SimpleNamespace(x=editor.button_positions[4]+15,y=20)), 4)
        editor.set_tool("rect")
        editor.press(SimpleNamespace(x=150, y=70))
        editor.release(SimpleNamespace(x=20, y=20))
        editor.finish()
        self.assertEqual(completed[0][1], "copy")
        self.assertEqual(completed[0][0].size, (420, 90))
        self.assertEqual(self.root.state(), "withdrawn")
        completed[0][0].close()

    def test_floating_is_movable_and_enabled_state_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            clicked = []
            button = FloatingButton(self.root, lambda: clicked.append(True), lambda: None, tmp)
            button.show()
            self.root.update()
            button._press(SimpleNamespace(x_root=100, y_root=100))
            button._drag(SimpleNamespace(x_root=70, y_root=120))
            button._release(None)
            self.assertFalse(clicked)
            button.hide()
            self.assertFalse(button.default_enabled())
            button.set_enabled(True)
            button.show()
            self.root.update()
            button._press(SimpleNamespace(x_root=100, y_root=100))
            button._release(None)
            self.assertTrue(clicked)
            self.assertTrue(FloatingButton(self.root, lambda: None, lambda: None, tmp).default_enabled())
            button.destroy()

    def test_floating_color_updates_visible_icon_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            button = FloatingButton(self.root, lambda: None, lambda: None, tmp)
            self.assertEqual(button.color, "#16a34a")
            button.show()
            self.root.update()
            original_icon = str(button.icon)
            button.set_enabled(False)
            button.set_color("#2563EB")
            self.assertNotEqual(str(button.icon), original_icon)
            restarted = FloatingButton(self.root, lambda: None, lambda: None, tmp)
            self.assertEqual(restarted.color, "#2563eb")
            self.assertFalse(restarted.default_enabled())
            with self.assertRaises(ValueError):
                button.set_color("invalid")
            icon = button.icon_image(color="#ffffff")
            self.assertEqual(icon.getpixel((0, 0))[3], 0)
            self.assertLess(icon.getpixel((17, 27))[0], 100)
            icon.close()
            button.destroy()

    def test_display_icon_has_no_dark_border_or_partial_alpha_halo(self):
        for hover in (False, True):
            image = FloatingButton.display_icon_image(hover)
            self.assertEqual(set(image.getchannel("A").tobytes()), {0, 255})
            for x in range(image.width):
                for y in range(image.height):
                    r, g, b, alpha = image.getpixel((x, y))
                    if alpha:
                        self.assertGreaterEqual(g, 150)
            image.close()


if __name__ == "__main__":
    unittest.main()


class FooterLayoutTests(unittest.TestCase):
    def test_progress_and_status_remain_visible_during_ocr_at_minimum_size(self):
        import threading, time
        from unittest.mock import patch, Mock
        from desktop.app import App
        from desktop.retention import CacheRetention
        root=tk.Tk()
        app=None
        release=threading.Event()
        try:
            with tempfile.TemporaryDirectory() as directory:
                floating=Mock()
                floating.default_enabled.return_value=False
                with patch('desktop.app.CacheRetention', return_value=CacheRetention(directory)), patch('desktop.app.FloatingButton',return_value=floating), patch.object(App,'initialize',return_value=Mock()):
                    app=App(root)
                deadline=time.monotonic()+2
                while app.busy and time.monotonic()<deadline:
                    root.update();time.sleep(.02)
                self.assertFalse(app.busy)
                root.geometry('820x760')
                app.set_image(Image.new('RGB',(420,180),'white'))
                def recognize(_):
                    release.wait(2)
                    return SimpleNamespace(txts=['Hello world'])
                app.engine=recognize
                app.recognize()
                deadline=time.monotonic()+.4
                while time.monotonic()<deadline:
                    root.update();time.sleep(.02)
                self.assertTrue(app.busy)
                self.assertIn('正在识字',app.original_heading.get())
                self.assertIn('已用',app.status.get())
                self.assertTrue(app.progress.winfo_viewable())
                self.assertLessEqual(app.progress.winfo_rooty()+app.progress.winfo_height(),root.winfo_rooty()+root.winfo_height())
                status=[w for w in app.progress.master.winfo_children() if isinstance(w,tk.ttk.Label) and str(w.cget('textvariable'))==str(app.status)][0]
                self.assertLessEqual(status.winfo_rooty()+status.winfo_height(),root.winfo_rooty()+root.winfo_height())
                release.set()
                deadline=time.monotonic()+2
                while app.busy and time.monotonic()<deadline:
                    root.update();time.sleep(.02)
                self.assertIn('Hello world',app.original.get('1.0','end'))
                app.close();app=None
        finally:
            release.set()
            if app:
                app.busy=False;app.close()
            else:
                try:
                    root.destroy()
                except tk.TclError:
                    pass
