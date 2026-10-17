import sys
import tempfile
import time
import unittest
from pathlib import Path

from desktop.floating import FloatingButton
from desktop.tray import SystemTray


@unittest.skipUnless(sys.platform == "win32", "Windows notification area only")
class SystemTrayTests(unittest.TestCase):
    def _icon(self, directory):
        path = Path(directory) / "tray.ico"
        image = FloatingButton.icon_image()
        try:
            image.save(path, format="ICO", sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48)])
        finally:
            image.close()
        return path

    def test_native_notification_icon_starts_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            actions = []
            tray = SystemTray(
                self._icon(directory),
                schedule=lambda action: actions.append(action),
                capture=lambda: None,
                translate=lambda: None,
                show_main=lambda: None,
                toggle_floating=lambda: None,
                floating_enabled=lambda: True,
                exit_app=lambda: None,
            )
            self.assertTrue(tray.start())
            self.assertTrue(tray.hwnd)
            self.assertIsNone(tray.error)
            tray.stop()
            self.assertIsNone(tray.hwnd)

    def test_menu_actions_are_marshaled_to_ui_scheduler(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduled = []
            called = []
            tray = SystemTray(
                self._icon(directory),
                schedule=lambda action: scheduled.append(action),
                capture=lambda: called.append("capture"),
                translate=lambda: called.append("translate"),
                show_main=lambda: called.append("show"),
                toggle_floating=lambda: called.append("floating"),
                floating_enabled=lambda: True,
                exit_app=lambda: called.append("exit"),
            )
            for command in (
                tray.MENU_CAPTURE,
                tray.MENU_TRANSLATE,
                tray.MENU_SHOW,
                tray.MENU_FLOATING,
                tray.MENU_EXIT,
            ):
                tray._dispatch_menu(command)
            self.assertEqual(len(scheduled), 5)
            for action in scheduled:
                action()
            self.assertEqual(
                called,
                ["capture", "translate", "show", "floating", "exit"],
            )


if __name__ == "__main__":
    unittest.main()
