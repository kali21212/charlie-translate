import json
import tempfile
import unittest
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from desktop.hotkeys import Hotkeys, IDS, parse_hotkey, event_hotkey
from desktop.app import App


class FakeWindows:
    def __init__(self):
        self.registered = {}
        self.blocked = set()

    def RegisterHotKey(self, hwnd, identifier, modifiers, key):
        combination = (modifiers, key)
        if combination in self.blocked or combination in self.registered.values():
            return 0
        self.registered[identifier] = combination
        return 1

    def UnregisterHotKey(self, hwnd, identifier):
        self.registered.pop(identifier, None)
        return 1


class HotkeyTests(unittest.TestCase):
    def test_validation_and_equivalent_combinations(self):
        self.assertEqual(parse_hotkey(' shift + ctrl + f02 '), ('Ctrl+Shift+F2', 0x4006, 0x71))
        for value in ('Q', 'Ctrl+Ctrl+Q', 'Ctrl+F13', 'Ctrl++', 'Win+Q', 'Ctrl+中'):
            with self.assertRaises(ValueError):
                parse_hotkey(value)
        with self.assertRaises(ValueError):
            Hotkeys.validate({'capture': 'Alt+Ctrl+Q', 'translate': 'Ctrl+Alt+Q'})

    def test_swap_persistence_conflict_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            api = FakeWindows()
            keys = Hotkeys(directory, api)
            keys.start()
            swapped = {'capture': 'Ctrl+Alt+T', 'translate': 'Ctrl+Alt+Q'}
            keys.apply(swapped)
            self.assertEqual(keys.active, swapped)
            self.assertEqual(Hotkeys(directory, api).values, swapped)
            before = dict(api.registered)
            api.blocked.add((0x4006, ord('Z')))
            with self.assertRaises(ValueError):
                keys.apply({'capture': 'Ctrl+Shift+X', 'translate': 'Ctrl+Shift+Z'})
            self.assertEqual(api.registered, before)
            self.assertEqual(keys.values, swapped)
            self.assertEqual(json.loads(keys.path.read_text()), swapped)
            keys.close()
            self.assertEqual(api.registered, {})

    def test_disk_failure_rolls_back_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            api = FakeWindows()
            keys = Hotkeys(directory, api)
            keys.start()
            before = dict(api.registered)
            with patch('desktop.hotkeys.Path.replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    keys.apply({'capture': 'Ctrl+Shift+X', 'translate': 'Ctrl+Shift+Y'})
            self.assertEqual(api.registered, before)
            self.assertEqual(keys.active, keys.values)

    def test_translation_capture_skips_editor_and_runs_ocr(self):
        app = App.__new__(App)
        app.capture_translate = True
        app.floating = Mock()
        app.floating_enabled = SimpleNamespace(get=lambda: True)
        app.set_image, app.show_main, app.recognize, app.copy_image = Mock(), Mock(), Mock(), Mock()
        image = Image.new('RGB', (100, 30))
        with patch('desktop.app.ScreenshotEditor') as editor:
            app.selected(image, (10, 20))
            editor.assert_not_called()
        app.set_image.assert_called_once_with(image)
        app.recognize.assert_called_once()
        app.copy_image.assert_called_once()
        self.assertTrue(app.capture_auto_translate)
        app.original, app.status, app.original_heading = Mock(), Mock(), Mock()
        app.set_translation, app.translate = Mock(), Mock()
        app.recognized('Hello')
        app.translate.assert_called_once()
        self.assertFalse(app.capture_auto_translate)
        image.close()

    def test_main_text_shortcut_consumes_event(self):
        app = App.__new__(App)
        app.translate = Mock()
        self.assertEqual(app.translate_shortcut(), 'break')
        app.translate.assert_called_once()

    def test_function_keys_and_recorded_modifier_keys(self):
        self.assertEqual(parse_hotkey('f1'), ('F1', 0x4000, 0x70))
        self.assertEqual(parse_hotkey('F12'), ('F12', 0x4000, 0x7b))
        self.assertEqual(event_hotkey(SimpleNamespace(keysym='F2', state=0)), 'F2')
        self.assertEqual(event_hotkey(SimpleNamespace(keysym='q', state=0x20005)), 'Ctrl+Alt+Shift+Q')

    def test_capture_copies_before_opening_editor_and_recopies_finished_image(self):
        app = App.__new__(App)
        app.capture_translate = False
        app.root = Mock()
        image = Image.new('RGB', (100, 30))
        order = []
        app.set_image = lambda value: (order.append('image'), value.close())
        app.copy_image = lambda: order.append('copy') or True
        app.floating = None
        app.status = Mock()
        with patch('desktop.app.ScreenshotEditor', side_effect=lambda *args, **kwargs: order.append('editor')):
            app.selected(image, (10,20))
        self.assertEqual(order, ['image','copy','editor'])
        app.editor_done(image)
        self.assertEqual(order[-2:], ['image','copy'])

    def test_owned_key_recording_dialog_saves_f1_f2_and_resumes_after_cancel(self):
        root = tk.Tk()
        try:
            with tempfile.TemporaryDirectory() as directory:
                app = App.__new__(App)
                app.root, app.closed, app.status = root, False, tk.StringVar()
                app.hotkeys = Hotkeys(directory, FakeWindows())
                app.hotkeys.start()
                app.configure_hotkeys()
                root.update()
                self.assertEqual(app.hotkeys.active, {})
                def children(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from children(child)
                entries = [w for w in children(app.hotkey_dialog) if isinstance(w,ttk.Entry)]
                for entry, key in zip(entries, ('F1','F2')):
                    entry.focus_force()
                    root.update()
                    entry.event_generate('<KeyPress>', keysym=key)
                    root.update()
                    self.assertEqual(entry.get(), key)
                for widget in children(app.hotkey_dialog):
                    if isinstance(widget,ttk.Button) and widget.cget('text') == '保存':
                        widget.invoke()
                        break
                self.assertEqual(app.hotkeys.active, {'capture':'F1','translate':'F2'})
                self.assertEqual(Hotkeys(directory,FakeWindows()).values, app.hotkeys.values)
                app.configure_hotkeys()
                self.assertEqual(app.hotkeys.active, {})
                app.hotkey_dialog.destroy()
                self.assertEqual(app.hotkeys.active, {'capture':'F1','translate':'F2'})
                app.hotkeys.close()
        finally:
            root.destroy()

    def test_numlock_is_not_alt_and_physical_alt_is_recorded(self):
        self.assertEqual(event_hotkey(SimpleNamespace(keysym='F6',state=8)), 'F6')
        app=App.__new__(App)
        variable=Mock()
        with patch('desktop.app.ctypes.windll.user32.GetKeyState', return_value=0):
            app.record_hotkey(SimpleNamespace(keysym='F6',state=8), variable)
        variable.set.assert_called_once_with('F6')
        variable.reset_mock()
        with patch('desktop.app.ctypes.windll.user32.GetKeyState', side_effect=lambda key: 0x8000 if key==0x12 else 0):
            app.record_hotkey(SimpleNamespace(keysym='F6',state=8), variable)
        variable.set.assert_called_once_with('Alt+F6')

    def test_stale_progress_timer_cannot_overwrite_completed_task(self):
        app=App.__new__(App)
        app.closed=False
        app.busy=True
        app.task_serial=2
        app.task_started=0
        app.task_caption='识字中'
        app.status,app.root=Mock(),Mock()
        app.update_task_progress(1)
        app.status.set.assert_not_called()
        app.busy=False
        app.update_task_progress(2)
        app.status.set.assert_not_called()
        app.root.after.assert_not_called()

    def test_dedicated_message_thread_delivers_hotkeys_to_tk_poll(self):
        import ctypes, queue
        from desktop.hotkeys import WindowsHotkeyPump, IDS
        pump=WindowsHotkeyPump()
        try:
            self.assertTrue(pump.RegisterHotKey(None, 0x6001, 0x4006, 0x7b))
            self.assertTrue(ctypes.windll.user32.PostThreadMessageW(pump.thread_id, 0x312, IDS['capture'], 0))
            identifier=pump.events.get(timeout=2)
            app=App.__new__(App)
            app.hotkey_api=SimpleNamespace(events=queue.Queue())
            app.hotkey_api.events.put(identifier)
            app.capture,app.root=Mock(),Mock()
            app.closed=False
            app.poll_hotkey()
            app.capture.assert_called_once_with()
            app.capture.reset_mock()
            app.hotkey_api.events.put(IDS['translate'])
            app.poll_hotkey()
            app.capture.assert_called_once_with(translate=True)
            pump.UnregisterHotKey(None, 0x6001)
        finally:
            pump.shutdown()
