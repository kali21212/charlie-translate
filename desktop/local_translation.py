"""Fixed, authenticated offline MTranServer child; no cloud endpoints."""
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


class LocalTranslation:
    def __init__(self, root):
        self.root = Path(root)
        self.process = None
        self.token = secrets.token_urlsafe(32)
        self.state = None
        # Ignore system proxy environment and forbid redirects, even to loopback.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *_args):
                return None
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def start(self):
        if self.process and self.process.poll() is None:
            return
        node = self.root / "translation" / "node.exe"
        entry = self.root / "translation" / "node_modules" / "mtranserver" / "dist" / "main.js"
        if not node.is_file() or not entry.is_file():
            raise RuntimeError("本地翻译组件缺失，请使用完整便携文件夹")
        self.state = tempfile.TemporaryDirectory(prefix="Charlie-translation-")
        shutil.copyfile(self.root / "translation" / "records.json", Path(self.state.name) / "records.json")
        env = {k: v for k, v in os.environ.items() if not k.startswith("MT_") and k not in ("NODE_OPTIONS", "NODE_PATH")}
        env.update({"MT_LOG_TO_FILE": "false", "MT_LOG_CONSOLE": "false", "MT_LOG_REQUESTS": "false"})
        self.process = subprocess.Popen([
            str(node), "--require", str(self.root / "translation" / "offline-guard.cjs"),
            str(entry), "--host", "127.0.0.1", "--port", "8991",
            "--model-dir", str(self.root / "translation" / "models"),
            "--config-dir", self.state.name, "--offline", "--no-ui",
            "--no-check-update", "--no-log-console", "--api-token", self.token,
        ], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(60):
            if self.process.poll() is not None:
                raise RuntimeError("本地翻译服务未启动，8991 端口可能被占用")
            try:
                self.request("/languages", None)
                return
            except (OSError, ValueError):
                time.sleep(0.1)
        raise RuntimeError("本地翻译服务启动超时")

    def request(self, path, body):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request("http://127.0.0.1:8991" + path, data=data,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.token})
        with self.client.open(request, timeout=60) as response:
            raw = response.read(100_001)
            if len(raw) > 100_000:
                raise ValueError("本机翻译响应过长")
            return json.loads(raw)

    def translate(self, text):
        if not text.strip() or len(text) > 12000:
            raise ValueError("请填写原文，且不超过 12000 字")
        self.start()
        result = self.request("/kiss", {"text": text, "from": "en", "to": "zh-Hans"})
        # The official single-text kiss API returns {text: string, src: string}.
        output = result.get("text") if isinstance(result, dict) else None
        if not isinstance(output, str):
            raise ValueError("本机翻译返回无效结果")
        return output

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.state:
            self.state.cleanup()
