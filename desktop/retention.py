"""Retention policy for Charlie-managed desktop cache files."""
import json
import os
import time
from pathlib import Path

DEFAULT_RETENTION_DAYS = 7
ALLOWED_RETENTION_DAYS = (0, 1, 3, 7, 14, 30)


class CacheRetention:
    def __init__(self, root=None):
        base = Path(root) if root else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CharlieTranslate"
        self.root = base
        self.config_path = base / "settings.json"
        config = self._load_config()
        self.cache_dir = Path(config.get("cacheDirectory") or base / "cache")
        self.save_directory = Path(config.get("saveDirectory") or Path.home() / "Pictures" / "CharlieTranslate")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.days = self._load_days()

    def _load_config(self):
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _load_days(self):
        try:
            data = self._load_config()
            days = int(data.get("cacheRetentionDays", DEFAULT_RETENTION_DAYS))
            return days if days in ALLOWED_RETENTION_DAYS else DEFAULT_RETENTION_DAYS
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return DEFAULT_RETENTION_DAYS

    def set_days(self, days):
        days = int(days)
        if days not in ALLOWED_RETENTION_DAYS:
            raise ValueError("unsupported retention period")
        self.days = days
        self._save_config()
        self.cleanup()

    def _save_config(self):
        self.root.mkdir(parents=True, exist_ok=True)
        config = self._load_config()
        config.update({"cacheRetentionDays": self.days, "cacheDirectory": str(self.cache_dir), "saveDirectory": str(self.save_directory)})
        self.config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    def set_cache_directory(self, directory):
        # Always isolate automatically deleted files from the user's other files.
        target = Path(directory).resolve() / "CharlieTranslateCache"
        target.mkdir(parents=True, exist_ok=True)
        self.cache_dir = target
        self._save_config()

    def set_save_directory(self, directory):
        self.save_directory = Path(directory).resolve()
        self.save_directory.mkdir(parents=True, exist_ok=True)
        self._save_config()
    def cleanup(self, now=None):
        now = time.time() if now is None else float(now)
        threshold = now if self.days == 0 else now - self.days * 86400
        removed = 0
        for path in list(self.cache_dir.rglob("*")):
            try:
                if path.is_file() and path.stat().st_mtime < threshold:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        for path in sorted(self.cache_dir.rglob("*"), reverse=True):
            try:
                if path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
            except OSError:
                pass
        return removed

    def cache_path(self, name):
        safe = Path(name).name
        if not safe:
            raise ValueError("invalid cache file name")
        return self.cache_dir / safe

    def close_session(self):
        if self.days == 0:
            for path in list(self.cache_dir.rglob("*")):
                try:
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass
