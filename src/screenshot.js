import browser from "webextension-polyfill";
import { createWorker } from "tesseract.js";
// Private extension document: no webpage resources, UI or remote OCR assets.
browser.runtime.onMessage.addListener((message, sender) => {
  if (message.action !== "charlieScreenshotOcrEngine") return false;
  if (sender.id !== browser.runtime.id || sender.tab) return false;
  return recognize(message.args);
});
async function recognize({ image, language }) {
  let worker;
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new Error("本地识字超时，请缩小范围后重试")),
      90000
    );
  });
  try {
    return await Promise.race([
      timeout,
      (async () => {
        worker = await createWorker(language, 1, {
          workerPath: browser.runtime.getURL("ocr/worker.min.js"),
          corePath: browser.runtime.getURL("ocr/tesseract-core-lstm.wasm.js"),
          langPath: browser.runtime.getURL("ocr"),
          workerBlobURL: false,
          gzip: false,
          cacheMethod: "none",
        });
        const result = await worker.recognize(image);
        return { text: result.data.text };
      })(),
    ]);
  } catch (error) {
    return { error: error.message || String(error) };
  } finally {
    clearTimeout(timer);
    await worker?.terminate();
  }
}
