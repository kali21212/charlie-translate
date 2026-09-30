import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace
from PIL import Image
from services.ocr.server import Handler, ThreadingHTTPServer, decode_png, create_engine
from desktop.app import region
from desktop.editor import apply_redaction, ScreenshotEditor
from desktop.retention import CacheRetention
from desktop.translation_bridge import (
    TranslationBridgeHandler,
    BRIDGE_HEADER,
    BRIDGE_VALUE,
    normalize_langs,
)

ROOT = Path(__file__).resolve().parents[2]


class SecurityTests(unittest.TestCase):
    def test_network_guard_blocks_before_connecting(self):
        code = "from desktop.privacy import install_network_guard; import socket; install_network_guard(); socket.create_connection(('203.0.113.1',443),timeout=1)"
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("blocks external", result.stderr)

    def test_node_guard_blocks_downloads_and_external_tcp(self):
        code = "const net=require('net');try{net.connect(443,'example.com');process.exit(2)}catch(e){}fetch('https://example.com').then(()=>process.exit(3)).catch(()=>process.exit(0));"
        result = subprocess.run(["node", "--require", str(ROOT / "desktop/offline-guard.cjs"), "-e", code], capture_output=True)
        self.assertEqual(result.returncode, 0)

    def test_crop_reverse_drag_clips_bounds_and_rejects_tiny(self):
        self.assertEqual(region((60,70),(-10,-20),100,100),(0,0,60,70))
        with self.assertRaises(ValueError): region((1,1),(2,2),100,100)

    def test_png_rejects_urls_invalid_data_and_large_dimensions(self):
        with self.assertRaises(ValueError): decode_png("https://example.com/image.png")
        with self.assertRaises(ValueError): decode_png("data:image/png;base64,dGVzdA==")
        image=Image.new("RGB",(4001,4000)); stream=io.BytesIO();image.save(stream,format="PNG")
        with self.assertRaises(ValueError): decode_png("data:image/png;base64,"+base64.b64encode(stream.getvalue()).decode())

    def test_redaction_replaces_base_pixels_without_snapshot(self):
        image=Image.new("RGB",(20,20),"white")
        for mode in ("redact_pixel","redact_blur","redact_solid"):
            candidate=image.copy()
            apply_redaction(candidate,(5,5,15,15),mode,"#000000")
            if mode == "redact_solid":
                self.assertEqual(candidate.getpixel((10,10)),(0,0,0))
            candidate.close()
        image.close()


class EditorTests(unittest.TestCase):
    def test_reverse_drag_export_and_chinese_annotations(self):
        editor = ScreenshotEditor.__new__(ScreenshotEditor)
        editor.base = Image.new("RGB", (200, 100), "white")
        editor.annotations = [
            {"type": "rect", "points": [(80, 80), (10, 10)], "radius": 12, "width": 4, "color": "#ff0000"},
            {"type": "ellipse", "points": [(180, 80), (110, 10)], "width": 4, "color": "#0000ff"},
            {"type": "text", "p": (20, 35), "text": "你好世界", "color": "#000000", "width": 4},
        ]
        output = editor._flatten()
        self.assertEqual(output.getpixel((10, 40)), (255, 0, 0))
        self.assertEqual(output.getpixel((110, 45)), (0, 0, 255))
        self.assertTrue(any(output.getpixel((x, y)) != (255, 255, 255) for x in range(25, 70) for y in range(40, 65)))
        output.close(); editor.base.close()

    def test_privacy_commit_cannot_be_undone_after_new_annotations(self):
        editor = ScreenshotEditor.__new__(ScreenshotEditor)
        editor.base = Image.new("RGB", (30, 30), "white")
        editor.annotations = []
        editor.undo_stack = [[{"type": "text", "text": "old"}]]
        editor.redo_stack = [[{"type": "text", "text": "old"}]]
        editor.color = "#000000"
        editor.status = SimpleNamespace(set=lambda text: None)
        editor._render = lambda *args: None
        editor._commit_redaction({"type": "redact_solid", "points": [(20, 20), (5, 5)]})
        self.assertEqual(editor.undo_stack, [])
        self.assertEqual(editor.redo_stack, [])
        editor._snapshot()
        editor.annotations.append({"type": "line"})
        editor.undo(); editor.undo(); editor.redo()
        self.assertEqual(editor.base.getpixel((10, 10)), (0, 0, 0))
        editor.base.close()


class RetentionTests(unittest.TestCase):
    def test_custom_paths_survive_restart_without_deleting_user_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_file = root / "keep.png"
            user_file.write_bytes(b"user image")
            retention = CacheRetention(root / "settings")
            retention.set_cache_directory(root)
            retention.set_save_directory(root / "saved")
            retention.set_days(0)
            retention.cache_path("temporary.png").write_bytes(b"cache")
            retention.close_session()
            restarted = CacheRetention(root / "settings")
            self.assertEqual(restarted.cache_dir, root.resolve() / "CharlieTranslateCache")
            self.assertEqual(restarted.save_directory, root.resolve() / "saved")
            self.assertEqual(restarted.days, 0)
            self.assertTrue(user_file.exists())

    def test_default_is_seven_days_and_expired_cache_is_removed(self):
        import tempfile
        import time
        with tempfile.TemporaryDirectory() as tmp:
            retention=CacheRetention(tmp)
            self.assertEqual(retention.days,7)
            old=retention.cache_path("old.png")
            old.write_bytes(b"x")
            os.utime(old,(time.time()-8*86400,time.time()-8*86400))
            self.assertEqual(retention.cleanup(),1)
            self.assertFalse(old.exists())
            retention.set_days(0)
            current=retention.cache_path("session.tmp")
            current.write_bytes(b"x")
            retention.close_session()
            self.assertFalse(current.exists())


class TranslationBridgeTests(unittest.TestCase):
    def setUp(self):
        class StubTranslation:
            def translate_request(self, text, source, target):
                return {"text": "你好", "src": source}
            def translate_many(self, texts, source, target):
                return [{"text": f"译:{text}", "src": source} for text in texts]
        self.server=ThreadingHTTPServer(("127.0.0.1",0),TranslationBridgeHandler)
        self.server.translation=StubTranslation()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f"http://127.0.0.1:{self.server.server_port}"
        self.client=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def post(self,body,headers=None):
        headers={
            "Content-Type":"application/json",
            BRIDGE_HEADER:BRIDGE_VALUE,
            **(headers or {}),
        }
        request=urllib.request.Request(
            self.url+"/kiss",
            data=json.dumps(body).encode(),
            headers=headers,
        )
        try:
            with self.client.open(request,timeout=2) as response:
                return response.status,json.load(response)
        except urllib.error.HTTPError as error:
            return error.code,json.load(error)

    def test_single_and_batch_translation(self):
        self.assertEqual(normalize_langs("auto","zh-CN"),("en","zh-Hans"))
        status,result=self.post({"text":"Hello","from":"auto","to":"zh-CN"})
        self.assertEqual(status,200);self.assertEqual(result["text"],"你好")
        status,result=self.post({"texts":["A","B"],"from":"en","to":"zh-Hans"})
        self.assertEqual(status,200)
        self.assertEqual([item["text"] for item in result["translations"]],["译:A","译:B"])

    def test_web_origin_or_missing_header_is_rejected(self):
        self.assertEqual(self.post({"text":"x"},{"Origin":"https://example.com"})[0],403)
        request=urllib.request.Request(
            self.url+"/kiss",
            data=b'{"text":"x"}',
            headers={"Content-Type":"application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.client.open(request,timeout=2)
        self.assertEqual(caught.exception.code,403)


class LocalApiTests(unittest.TestCase):
    def setUp(self):
        self.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        self.calls=[]
        def recognize(raw):
            self.calls.append(raw)
            return SimpleNamespace(txts=("Hello",))
        self.server.engine=recognize
        self.server.ocr_lock=threading.Lock()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f"http://127.0.0.1:{self.server.server_port}"
        self.client=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def post(self,headers,body):
        request=urllib.request.Request(self.url+"/ocr",data=json.dumps(body).encode(),headers=headers)
        try:
            with self.client.open(request,timeout=2) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)

    def test_webpages_wrong_host_and_missing_header_never_reach_engine(self):
        for headers in [{},{"X-Charlie-OCR":"1","Origin":"https://example.com"},{"X-Charlie-OCR":"1","Host":"evil.example"}]:
            try:
                self.assertEqual(self.post(headers,{"image":"x"})[0],403)
            except (ConnectionAbortedError, ConnectionResetError) as error:
                # Closing an unauthorized POST without reading its body can reset
                # Windows TCP. Both outcomes must still leave the engine untouched.
                if sys.platform != "win32" or error.winerror not in (10053,10054):
                    raise
            self.assertEqual(self.calls,[])
        self.assertEqual(self.calls,[])

    def test_valid_local_png_and_invalid_json_object(self):
        stream=io.BytesIO();Image.new("RGB",(20,20)).save(stream,format="PNG")
        headers={"X-Charlie-OCR":"1","Content-Type":"application/json"}
        self.assertEqual(self.post(headers,[])[0],400)
        status,result=self.post(headers,{"image":"data:image/png;base64,"+base64.b64encode(stream.getvalue()).decode()})
        self.assertEqual(status,200);self.assertEqual(result["text"],"Hello");self.assertEqual(len(self.calls),1)


@unittest.skipUnless(os.environ.get("CHARLIE_OCR_MODELS"),"Set CHARLIE_OCR_MODELS for real offline inference")
class RealOcrTests(unittest.TestCase):
    def test_fixture_english_and_chinese(self):
        engine=create_engine(Path(os.environ["CHARLIE_OCR_MODELS"]))
        result=engine(str(ROOT/"testdata/screenshot/ocr-fixture.png"))
        text="".join(result.txts)
        self.assertIn("Charlie",text);self.assertIn("Translate",text);self.assertIn("你好世界",text)


if __name__=="__main__":unittest.main()
