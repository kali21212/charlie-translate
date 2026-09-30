import browser from "webextension-polyfill";
import { recognizeScreenshot, cancelScreenshotOcr } from "./screenshotOcr";
jest.mock("webextension-polyfill", () => ({
  runtime: { id: "self", sendMessage: jest.fn() },
}));
const sender = {
  id: "self",
  frameId: 0,
  tab: { id: 4 },
  documentId: "doc",
  url: "https://example.com/",
};
const args = {
  image: "data:image/png;base64,test",
  language: "eng",
  job: "one",
};
beforeEach(() => {
  globalThis.chrome = {
    offscreen: {
      createDocument: jest.fn().mockResolvedValue(),
      closeDocument: jest.fn().mockResolvedValue(),
    },
  };
  browser.runtime.sendMessage.mockReset().mockResolvedValue({ text: "Hello" });
});
test("uses a private local worker document and closes it after completion", async () => {
  expect(await recognizeScreenshot(args, sender)).toEqual({ text: "Hello" });
  expect(globalThis.chrome.offscreen.createDocument).toHaveBeenCalledWith(
    expect.objectContaining({ url: "screenshot.html", reasons: ["WORKERS"] })
  );
  expect(globalThis.chrome.offscreen.closeDocument).toHaveBeenCalledTimes(1);
});
test("invalid callers and non-PNG input do not open a document", async () => {
  await expect(
    recognizeScreenshot(args, { ...sender, id: "other" })
  ).rejects.toThrow("sender");
  await expect(
    recognizeScreenshot({ ...args, image: "https://remote/image" }, sender)
  ).rejects.toThrow("input");
  expect(globalThis.chrome.offscreen.createDocument).not.toHaveBeenCalled();
});
test("creation failure does not close another existing document", async () => {
  globalThis.chrome.offscreen.createDocument.mockRejectedValue(
    new Error("already exists")
  );
  await expect(recognizeScreenshot(args, sender)).rejects.toThrow(
    "already exists"
  );
  expect(globalThis.chrome.offscreen.closeDocument).not.toHaveBeenCalled();
});
test("only the same document can cancel its pending OCR, concurrent OCR is rejected", async () => {
  let done;
  browser.runtime.sendMessage.mockImplementation(
    () =>
      new Promise((r) => {
        done = r;
      })
  );
  const running = recognizeScreenshot(args, sender);
  await Promise.resolve();
  await expect(recognizeScreenshot(args, sender)).rejects.toThrow("正在运行");
  await cancelScreenshotOcr(args, { ...sender, documentId: "another" });
  expect(globalThis.chrome.offscreen.closeDocument).not.toHaveBeenCalled();
  await cancelScreenshotOcr(args, sender);
  expect(globalThis.chrome.offscreen.closeDocument).toHaveBeenCalledTimes(1);
  done({ text: "Hello" });
  await running;
});
