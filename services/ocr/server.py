"""Charlie loopback OCR adapter. No image logging, remote images or runtime downloads."""
import base64
import hashlib
import io
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_BODY = 24_000_000
MAX_PIXELS = 16_000_000
SERVICE = "CharlieOCR/1"


def create_engine(model_dir):
    from rapidocr import RapidOCR, OCRVersion, ModelType
    for asset in json.loads((ROOT / "models.json").read_text()):
        path = model_dir / asset["name"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise ValueError("OCR model checksum mismatch: " + asset["name"])
    return RapidOCR(params={
        "Global.model_root_dir": str(model_dir),
        "Global.use_cls": False,
        "Global.log_level": "error",
        "Det.ocr_version": OCRVersion.PPOCRV5,
        "Det.model_type": ModelType.SERVER,
        "Det.model_path": str(model_dir / "ch_PP-OCRv5_det_server.onnx"),
        "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.model_type": ModelType.SERVER,
        "Rec.model_path": str(model_dir / "ch_PP-OCRv5_rec_server.onnx"),
        "Cls.model_path": str(model_dir / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"),
        "EngineConfig.onnxruntime.intra_op_num_threads": min(4, os.cpu_count() or 1),
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    })


def decode_png(value):
    from PIL import Image
    if not isinstance(value, str) or not value.startswith("data:image/png;base64,"):
        raise ValueError("PNG required")
    raw = base64.b64decode(value.split(",", 1)[1], validate=True)
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG required")
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != "PNG" or image.width * image.height > MAX_PIXELS:
            raise ValueError("Image too large")
        image.verify()
    return raw


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, *_args):
        pass

    def reply(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        # Custom header + no CORS stops webpages/form POSTs. Host prevents DNS rebinding.
        origin = self.headers.get("Origin", "")
        extension = bool(re.fullmatch(r"chrome-extension://[a-p]{32}", origin))
        return (self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
                and self.headers.get("X-Charlie-OCR") == "1"
                and (not origin or extension))

    def do_OPTIONS(self):
        self.reply(403, {"error": "Webpage access denied"})

    def do_GET(self):
        if self.path != "/health" or not self.allowed():
            return self.reply(403, {"error": "Access denied"})
        self.reply(200, {"service": SERVICE, "model": "PP-OCRv5 server", "ready": True})

    def do_POST(self):
        if self.path != "/ocr" or not self.allowed():
            return self.reply(403, {"error": "Access denied"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY or self.headers.get_content_type() != "application/json":
                return self.reply(413, {"error": "Invalid request size or type"})
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Invalid request")
            raw = decode_png(data.get("image"))
        except (ValueError, TypeError, OSError):
            return self.reply(400, {"error": "Invalid PNG input"})
        if not self.server.ocr_lock.acquire(blocking=False):
            return self.reply(409, {"error": "OCR busy; please retry shortly"})
        try:
            result = self.server.engine(raw)
            text = "\n".join(result.txts if result.txts is not None else ())
            if len(text) > 12000:
                return self.reply(413, {"error": "Too much text; select a smaller region"})
            self.reply(200, {"service": SERVICE, "text": text, "engine": "PP-OCRv5 server"})
        except Exception:
            self.reply(500, {"error": "OCR inference failed"})
        finally:
            self.server.ocr_lock.release()


def main():
    model_dir = ROOT / "models"
    engine = create_engine(model_dir)
    server = ThreadingHTTPServer(("127.0.0.1", 8990), Handler)
    server.engine = engine
    server.ocr_lock = threading.Lock()
    print("Charlie OCR ready: 127.0.0.1:8990; close this window to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
