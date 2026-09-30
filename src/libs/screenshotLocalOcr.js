// Fixed loopback endpoint. Never accept a URL from a webpage or follow redirects.
const ENDPOINT = "http://127.0.0.1:8990";
const SERVICE = "CharlieOCR/1";
export async function recognizeLocalScreenshot(image, signal) {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal.addEventListener("abort", cancel, { once: true });
  if (signal.aborted) cancel();
  let expired = false;
  const timer = setTimeout(() => {
    expired = true;
    cancel();
  }, 90000);
  const request = async (path, options = {}) => {
    const response = await fetch(ENDPOINT + path, {
      ...options,
      headers: { "X-Charlie-OCR": "1", "Content-Type": "application/json" },
      redirect: "error",
      credentials: "omit",
      cache: "no-store",
      signal: controller.signal,
    });
    const body = await response.text();
    if (body.length > 60000) throw new Error("本机 OCR 返回内容过长");
    const result = JSON.parse(body);
    if (!response.ok) throw new Error(result.error || "本机 OCR 处理失败");
    if (result.service !== SERVICE)
      throw new Error("8990 端口不是 Charlie OCR 服务");
    return result;
  };
  try {
    // Verify service identity before sending the screenshot.
    const health = await request("/health");
    if (health.ready !== true) throw new Error("本机 OCR 尚未就绪");
    const result = await request("/ocr", {
      method: "POST",
      body: JSON.stringify({ image }),
    });
    if (typeof result.text !== "string" || result.text.length > 12000)
      throw new Error("本机 OCR 返回的文字无效");
    return { text: result.text, engine: "PP-OCRv5 server" };
  } catch (error) {
    if (signal.aborted) throw new Error("已停止识字");
    if (expired) throw new Error("增强识字超时，请缩小范围后重试");
    if (error instanceof TypeError)
      throw new Error("本机增强 OCR 未连接。请先打开 Charlie Translate 桌面版");
    throw error;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", cancel);
  }
}
