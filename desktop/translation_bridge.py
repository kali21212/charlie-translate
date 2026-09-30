"""Loopback-only bridge that lets the Charlie browser extension reuse the
Desktop-bundled MTranServer without exposing its random bearer token.
"""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8992
BRIDGE_HEADER = "X-Charlie-Translate"
BRIDGE_VALUE = "desktop-v1"


def normalize_langs(source, target):
    source = (source or "auto").strip()
    target = (target or "zh-CN").strip()
    if source in ("auto", ""):
        source = "en"
    if source != "en":
        raise ValueError("当前桌面离线模型仅支持英文原文")
    if target in ("zh-CN", "zh", "zh-Hans"):
        target = "zh-Hans"
    else:
        raise ValueError("当前桌面离线模型仅支持翻译为简体中文")
    return source, target


class TranslationBridgeHandler(BaseHTTPRequestHandler):
    server_version = "CharlieTranslateBridge/1"

    def log_message(self, _format, *_args):
        return

    def _reject(self, code, message):
        data = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        origin = self.headers.get("Origin", "")
        extension = bool(re.fullmatch(r"chrome-extension://[a-p]{32}", origin))
        return (
            self.headers.get("Host") == f"{BRIDGE_HOST}:{self.server.server_port}"
            and self.headers.get(BRIDGE_HEADER) == BRIDGE_VALUE
            and (not origin or extension)
        )
    def do_OPTIONS(self):
        self._reject(403, "Browser pages are not allowed")

    def do_GET(self):
        if self.path != "/health" or not self._authorized():
            self._reject(403, "Local extension access only")
            return
        payload = json.dumps({
            "ok": True,
            "service": "Charlie Translate Desktop",
            "translation": "en->zh-Hans",
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _discard_request_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            return
        if 0 < length <= 200_000:
            try:
                self.rfile.read(length)
            except OSError:
                pass

    def do_POST(self):
        if self.path != "/kiss" or not self._authorized():
            # Consume a small rejected request body before replying so Windows
            # does not reset the socket while urllib is still sending it.
            self._discard_request_body()
            self._reject(403, "Local extension access only")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 200_000:
                raise ValueError("请求过大")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("请求格式无效")
            source, target = normalize_langs(body.get("from"), body.get("to"))
            texts = body.get("texts")
            if texts is not None:
                if not isinstance(texts, list) or not texts or len(texts) > 50:
                    raise ValueError("批量翻译数量无效")
                if any(not isinstance(text, str) for text in texts):
                    raise ValueError("批量翻译内容无效")
                if sum(len(text) for text in texts) > 20_000:
                    raise ValueError("批量翻译内容过长")
                result = self.server.translation.translate_many(texts, source, target)
                payload = {"translations": result}
            else:
                text = body.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > 12_000:
                    raise ValueError("翻译文字无效")
                result = self.server.translation.translate_request(text, source, target)
                payload = result
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except ValueError as error:
            self._reject(400, str(error))
        except Exception:
            self._reject(503, "桌面离线翻译服务暂不可用")


def start_translation_bridge(translation):
    server = ThreadingHTTPServer((BRIDGE_HOST, BRIDGE_PORT), TranslationBridgeHandler)
    server.translation = translation
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
