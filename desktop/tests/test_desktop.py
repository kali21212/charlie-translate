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
