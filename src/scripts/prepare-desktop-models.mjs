import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";
await mkdir("tmp/rapid-models", { recursive: true });
for (const asset of JSON.parse(
  await readFile("services/ocr/models.json", "utf8")
)) {
  const file = "tmp/rapid-models/" + asset.name;
  const hash = (b) => createHash("sha256").update(b).digest("hex");
  let bytes;
  try {
    bytes = await readFile(file);
  } catch (_) {
    /* download verified resource below */
  }
  if (!bytes || hash(bytes) !== asset.sha256) {
    const response = await fetch(asset.url, {
      signal: AbortSignal.timeout(120000),
    });
    if (!response.ok)
      throw new Error("OCR model download failed: " + asset.name);
    bytes = Buffer.from(await response.arrayBuffer());
    if (hash(bytes) !== asset.sha256)
      throw new Error("OCR model checksum mismatch: " + asset.name);
    await writeFile(file, bytes);
  }
}
