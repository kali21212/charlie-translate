# Upstream and provenance

Charlie Translate is an enhanced derivative of **KISS Translator**.

- Upstream: https://github.com/fishjar/kiss-translator
- Upstream default development branch at project start: `dev`
- Baseline: `8ce3888ad1faf5577b203e305ba58a3942b89627`
- License: GNU GPL v3
- Local upstream remote: `upstream`
- Our public repository: https://github.com/kali21212/charlie-translate
- Our default branch: `main`

## Reuse policy

We preserve upstream attribution and GPL-3.0 obligations. Charlie-specific changes are tracked in CHANGELOG.md and Git history. No upstream history is rewritten. Updates should flow:

`upstream -> integration branch -> tests/audit -> PR -> main -> release`

Additional projects are used only where their licenses and security posture are compatible. MTranServer is integrated by protocol/API and remains a separate Apache-2.0 project.

## Charlie V1 reuse review (2026-09-30)

Screenshot OCR now reuses RapidOCR 3.9.2 (Apache-2.0) and PP-OCRv5 server ONNX weights (PaddleOCR / Baidu, Apache-2.0), pinned by services/ocr/models.json. Tesseract and its assets were removed. Pillow is MIT-CMU; Tk/Python licenses and all collected Python dependency notices accompany the portable package.

Route B: adapt KISS Translator, preserving GPL source, author notices and Git history. It provides the existing DOM translation, selection/hover/input/subtitle UI, settings, caching and adapters. Upstream was active on the review date; inherited CRA dependencies require the documented repairs and a later tooling migration.

MTranServer is a separately installed API-only service. Inspected its Apache-2.0 LICENSE and `/kiss` controller/auth middleware at `f5672a986b5bb935064fc74d1a7074fde7469daf`; latest release reviewed: `v4.0.33` (2026-03-08). Requests accept `{texts, from, to}` or `{text, from, to}`, responses contain `text`/`src`, authentication accepts a bearer token. The browser client originally copied no server resources. The optional desktop portable package now bundles pinned MTranServer 4.0.33, official verified Node and English-to-Chinese model resources, with their separate notices. Protocol review is not a full audit of that independent service.

Charlie changes cover local defaults/adapter, privacy checks, extension names/homepage, compatible dependency patches, tests/CI and governance docs. Storage keys and existing saved settings are retained. `.env` keeps upstream web/userscript deployment references for compatibility; those clients are outside Charlie V1 Chrome validation. Fresh-install update checks are disabled.

Settings routing now uses React Router 7.18.4 directly (MIT LICENSE inspected from the installed package), replacing the v6 react-router-dom dependency. HashRouter/Routes/NavLink/Outlet interfaces remain declarative; routing and startup behavior are regression-tested. Test-only encoding API setup supplies Node implementations missing from CRA's jsdom; no runtime routing mocks or forced v7 transitive override are used.

Sync future upstream updates on an integration branch, then rerun test/audit/PR checks. Never push to upstream. Distributing modified binaries requires corresponding GPL source and preserved notices, including generated dependency license notices.

Desktop provenance: RapidOCR https://github.com/RapidAI/RapidOCR; PaddleOCR https://github.com/PaddlePaddle/PaddleOCR; Pillow https://github.com/python-pillow/Pillow. MTranServer https://github.com/xxnuo/MTranServer (Apache-2.0); translation engine https://github.com/browsermt/bergamot-translator (MPL-2.0); Firefox model weights https://github.com/mozilla/translations (MPL-2.0, upstream explicitly states model-file licensing). Model hashes and source record IDs are in desktop/translation-records.json. Node version/source/hash is in desktop/node-runtime.json. Umi-OCR (MIT) and NormCap (GPL-3.0-or-later) were evaluated; no code was copied. PyInstaller 6.22.3 has GPL terms with a bootloader exception; preserve its packaged notices.
