from types import SimpleNamespace
import tempfile
import unittest

from desktop.local_translation import LocalTranslation
from desktop.retention import CacheRetention
from desktop.text_layout import format_ocr_result, reflow_plain_text


def box(x, y, width, height=20):
    return [
        [x, y],
        [x + width, y],
        [x + width, y + height],
        [x, y + height],
    ]


class TextLayoutTests(unittest.TestCase):
    def result(self, texts, boxes):
        return SimpleNamespace(txts=texts, boxes=boxes)

    def test_wrapped_paragraph_is_reflowed(self):
        result = self.result(
            ["Snow Apps repository, providing source code", "for Snow Shot and Snow Image Viewer."],
            [box(0, 0, 310), box(0, 24, 300)],
        )
        self.assertEqual(
            format_ocr_result(result),
            "Snow Apps repository, providing source code for Snow Shot and Snow Image Viewer.",
        )

    def test_heading_and_body_stay_separate(self):
        result = self.result(
            ["Install Snow Shot on Windows", "Download the installer from Snow Shot releases."],
            [box(0, 0, 360, 38), box(0, 48, 420, 20)],
        )
        self.assertEqual(
            format_ocr_result(result),
            "Install Snow Shot on Windows\n\nDownload the installer from Snow Shot releases.",
        )

    def test_columns_keep_reading_order(self):
        result = self.result(
            ["Left first", "Right first", "left continues", "right continues"],
            [box(0, 0, 150), box(320, 0, 150), box(0, 24, 160), box(320, 24, 170)],
        )
        self.assertEqual(
            format_ocr_result(result),
            "Left first left continues\n\nRight first right continues",
        )

    def test_hyphen_and_cjk_spacing(self):
        result = self.result(
            ["This is trans-", "lation continued", "你好", "世界"],
            [box(0, 0, 150), box(0, 24, 170), box(300, 0, 40), box(300, 24, 40)],
        )
        self.assertEqual(
            format_ocr_result(result),
            "This is translation continued\n\n你好世界",
        )

    def test_large_gap_starts_new_paragraph(self):
        result = self.result(
            ["The first paragraph ends.", "Another paragraph starts here"],
            [box(0, 0, 250), box(0, 55, 270)],
        )
        self.assertEqual(
            format_ocr_result(result),
            "The first paragraph ends.\n\nAnother paragraph starts here",
        )

    def test_plain_text_fallback_removes_ocr_hard_wraps(self):
        self.assertEqual(
            reflow_plain_text("A long OCR line\ncontinued on screen\n\nSecond paragraph."),
            "A long OCR line continued on screen\n\nSecond paragraph.",
        )


class DocumentTranslationTests(unittest.TestCase):
    class StubTranslation(LocalTranslation):
        def __init__(self):
            self.batch_sizes = []

        def translate_request(self, text, source="en", target="zh-Hans"):
            self.batch_sizes.append((1, len(text)))
            return {"text": "译:" + text, "src": source}

        def translate_many(self, texts, source="en", target="zh-Hans"):
            self.batch_sizes.append((len(texts), sum(map(len, texts))))
            return [{"text": "译:" + text, "src": source} for text in texts]

    def test_document_translation_preserves_paragraphs(self):
        translator = self.StubTranslation()
        output = translator.translate_document("First paragraph.\n\nSecond paragraph.")
        self.assertEqual(output, "译:First paragraph.\n\n译:Second paragraph.")

    def test_long_document_is_batched_under_transport_limit(self):
        translator = self.StubTranslation()
        text = ("Sentence one. " * 900) + "\n\n" + ("Sentence two. " * 900)
        output = translator.translate_document(text)
        self.assertIn("\n\n", output)
        self.assertTrue(translator.batch_sizes)
        self.assertTrue(all(count <= 20 and size <= 18000 for count, size in translator.batch_sizes))


class UiSettingsTests(unittest.TestCase):
    def test_ui_settings_round_trip_without_clobbering_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            retention = CacheRetention(directory)
            retention.set_ui_setting("autoReflowOcr", False)
            retention.set_ui_setting("mainWindowGeometry", "1040x720+10+20")
            restarted = CacheRetention(directory)
            self.assertFalse(restarted.get_ui_setting("autoReflowOcr", True))
            self.assertEqual(
                restarted.get_ui_setting("mainWindowGeometry"),
                "1040x720+10+20",
            )
            self.assertEqual(restarted.days, 7)


if __name__ == "__main__":
    unittest.main()
