import { recognizeLocalScreenshot } from "./screenshotLocalOcr";
const reply = (body, ok = true) => ({
  ok,
  text: async () => JSON.stringify(body),
});
beforeEach(() => {
  global.fetch = jest
    .fn()
    .mockResolvedValue(
      reply({ service: "CharlieOCR/1", ready: true, text: "Hello" })
    );
});
test("verifies identity before sending PNG and forbids redirects", async () => {
  expect(
    await recognizeLocalScreenshot("PNG", new AbortController().signal)
  ).toEqual({ text: "Hello", engine: "PP-OCRv5 server" });
  expect(fetch.mock.calls[0][0]).toBe("http://127.0.0.1:8990/health");
  expect(fetch.mock.calls[1]).toEqual([
    "http://127.0.0.1:8990/ocr",
    expect.objectContaining({
      redirect: "error",
      credentials: "omit",
      body: JSON.stringify({ image: "PNG" }),
    }),
  ]);
});
test("a different local service never receives the screenshot", async () => {
  fetch.mockResolvedValue(reply({ service: "other", ready: true }));
  await expect(
    recognizeLocalScreenshot("private PNG", new AbortController().signal)
  ).rejects.toThrow("不是");
  expect(fetch).toHaveBeenCalledTimes(1);
});
test("missing service is actionable and does not fall back to cloud", async () => {
  fetch.mockRejectedValue(new TypeError("Failed to fetch"));
  await expect(
    recognizeLocalScreenshot("PNG", new AbortController().signal)
  ).rejects.toThrow("未连接");
  expect(fetch).toHaveBeenCalledTimes(1);
});
