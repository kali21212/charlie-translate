import { recognizeScreenshot, cancelScreenshotOcr } from "./screenshotOcr";
import { recognizeLocalScreenshot } from "./screenshotLocalOcr";
jest.mock("webextension-polyfill", () => ({ runtime: { id: "self" } }));
jest.mock("./screenshotLocalOcr", () => ({
  recognizeLocalScreenshot: jest.fn(),
}));
const sender = {
  id: "self",
  frameId: 0,
  tab: { id: 4 },
  documentId: "doc",
  url: "https://example.com/",
};
const args = { image: "data:image/png;base64,dGVzdA==", job: "one" };
beforeEach(() => recognizeLocalScreenshot.mockResolvedValue({ text: "Hello" }));
test("recognizes only through the enhanced local adapter", async () => {
  expect(await recognizeScreenshot(args, sender)).toEqual({ text: "Hello" });
  expect(recognizeLocalScreenshot).toHaveBeenCalledWith(
    args.image,
    expect.any(AbortSignal)
  );
});
test("rejects foreign callers and remote image URLs before processing", async () => {
  await expect(
    recognizeScreenshot(args, { ...sender, id: "other" })
  ).rejects.toThrow("sender");
  await expect(
    recognizeScreenshot({ ...args, image: "https://remote/image" }, sender)
  ).rejects.toThrow("input");
  expect(recognizeLocalScreenshot).not.toHaveBeenCalled();
});
test("cancellation binds to the same document and discards late text", async () => {
  let done, signal;
  recognizeLocalScreenshot.mockImplementation((_image, s) => {
    signal = s;
    return new Promise((r) => {
      done = r;
    });
  });
  const running = recognizeScreenshot(args, sender);
  await expect(recognizeScreenshot(args, sender)).rejects.toThrow("正在运行");
  await cancelScreenshotOcr(args, { ...sender, documentId: "other" });
  expect(signal.aborted).toBe(false);
  await cancelScreenshotOcr(args, sender);
  expect(signal.aborted).toBe(true);
  done({ text: "late" });
  await expect(running).rejects.toThrow("停止");
});
