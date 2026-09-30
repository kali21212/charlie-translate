"""Build a portable folder from pinned, preinstalled resources; no download at runtime."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "desktop"


def copy_checked(source, target, expected):
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise ValueError("Checksum mismatch: " + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main():
    # PyInstaller only cleans its dedicated build outputs, never user files.
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--windowed", "--name", "CharlieTranslate", "--paths", str(ROOT),
        "--distpath", str(OUT), "--workpath", str(ROOT / "tmp" / "desktop-pyinstaller"),
        "--specpath", str(ROOT / "tmp"), "--collect-data", "rapidocr",
        "--add-data", str(ROOT / "services/ocr/models.json") + ";services/ocr",
        str(ROOT / "desktop/launch.py")], check=True, cwd=ROOT)
    app = OUT / "CharlieTranslate"
    for asset in json.loads((ROOT / "services/ocr/models.json").read_text()):
        copy_checked(ROOT / "tmp/rapid-models" / asset["name"], app / "models" / asset["name"], asset["sha256"])
    runtime = json.loads((ROOT / "desktop/node-runtime.json").read_text())
    copy_checked(Path(shutil.which("node")), app / "translation/node.exe", runtime["sha256"])
    shutil.copytree(ROOT / "tmp/desktop-translation/node_modules", app / "translation/node_modules", dirs_exist_ok=True)
    shutil.copy2(ROOT / "desktop/offline-guard.cjs", app / "translation/offline-guard.cjs")
    records = json.loads((ROOT / "desktop/translation-records.json").read_text())
    shutil.copy2(ROOT / "desktop/translation-records.json", app / "translation/records.json")
    for record in records["data"]:
        name = record["name"]
        copy_checked(ROOT / "tmp/mtran-models/en_zh-Hans" / name, app / "translation/models/en_zh-Hans" / name, record["decompressedHash"])
    shutil.copytree(ROOT / "desktop/licenses", app / "licenses", dirs_exist_ok=True)
    shutil.copy2(ROOT / "tmp/NODE-LICENSE.txt", app / "licenses/NODE-LICENSE.txt")
    for base in (Path(sys.base_prefix), Path(sys.base_prefix) / "tcl"):
        for source in base.glob("**/license.terms"):
            target = app / "licenses/python-runtime" / source.relative_to(Path(sys.base_prefix))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source,target)
    for name in ("LICENSE.txt", "LICENSE"):
        source=Path(sys.base_prefix)/name
        if source.is_file(): shutil.copy2(source,app / "licenses/PYTHON-LICENSE.txt")
    for dist in importlib.metadata.distributions():
        for file in dist.files or ():
            if any(word in file.name.lower() for word in ("license", "copying", "notice")):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = app / "licenses/python" / dist.metadata["Name"] / str(file).replace("../", "")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    for name in ("LICENSE", "UPSTREAM.md", "SECURITY.md"):
        shutil.copy2(ROOT / name, app / name)
    shutil.copy2(ROOT / "docs/DESKTOP.md", app / "使用说明.md")
    shutil.copytree(ROOT / "desktop", app / "source/desktop", ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    shutil.copytree(ROOT / "services", app / "source/services", ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    manifest = [{"path": str(p.relative_to(app)).replace("\\", "/"),
                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
                for p in sorted(app.rglob("*")) if p.is_file()]
    (app / "FILES.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Portable application:", app)


if __name__ == "__main__":
    main()
