import { createWorker } from "tesseract.js";
import { prepareOcr } from "./prepare-ocr.mjs";
import { resolve } from "node:path";
import assert from "node:assert/strict";

await prepareOcr("tmp/ocr-runtime");
let worker;
try {
  worker = await createWorker("eng+chi_sim", 1, {
    langPath: resolve("tmp/ocr-runtime"),
    gzip: false,
    cacheMethod: "none",
  });
  const result = await worker.recognize("testdata/screenshot/ocr-fixture.png");
  assert.match(result.data.text, /Charlie Translate/i);
  assert.match(result.data.text.replace(/\s/g, ""), /截图翻译/);
  console.log("Real local English + Simplified Chinese OCR fixture passed");
} finally {
  await worker?.terminate();
}
