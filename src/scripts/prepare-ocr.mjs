import { readFile, mkdir, copyFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
import { createHash } from "node:crypto";

export async function prepareOcr(destination) {
  await mkdir(destination, { recursive: true });
  const require = createRequire(import.meta.url);
  const api = dirname(require.resolve("tesseract.js/package.json"));
  const core = dirname(
    createRequire(join(api, "package.json")).resolve(
      "tesseract.js-core/package.json"
    )
  );
  for (const [source, name] of [
    [join(api, "dist/worker.min.js"), "worker.min.js"],
    [join(api, "LICENSE.md"), "TESSERACT-JS-LICENSE.txt"],
    [join(core, "LICENSE"), "TESSERACT-CORE-LICENSE.txt"],
    [join(core, "tesseract-core-lstm.wasm.js"), "tesseract-core-lstm.wasm.js"],
    [join(core, "tesseract-core-lstm.wasm"), "tesseract-core-lstm.wasm"],
  ]) {
    await copyFile(source, join(destination, name));
  }
  const assets = JSON.parse(await readFile("docs/ocr-assets.json", "utf8"));
  await mkdir("tmp/ocr-models", { recursive: true });
  for (const asset of assets) {
    const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
    let bytes;
    try {
      bytes = await readFile(join("tmp/ocr-models", asset.name));
    } catch (_) {
      /* download below */
    }
    if (!bytes || hash(bytes) !== asset.sha256) {
      const response = await fetch(asset.url, {
        signal: AbortSignal.timeout(60000),
      });
      if (!response.ok)
        throw new Error(`OCR asset download failed: ${asset.name}`);
      bytes = Buffer.from(await response.arrayBuffer());
      if (hash(bytes) !== asset.sha256)
        throw new Error(`OCR asset checksum mismatch: ${asset.name}`);
      await writeFile(join("tmp/ocr-models", asset.name), bytes);
    }
    await writeFile(
      join(
        destination,
        asset.name === "LICENSE" ? "TESSDATA-LICENSE.txt" : asset.name
      ),
      bytes
    );
  }
  await copyFile("docs/ocr-assets.json", join(destination, "ASSETS.json"));
}
