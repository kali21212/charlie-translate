import browser from "webextension-polyfill";
let active;
const validSender = (sender) =>
  sender?.id === browser.runtime.id &&
  sender.frameId === 0 &&
  Number.isInteger(sender.tab?.id) &&
  /^https?:\/\//.test(sender.url || "");
export async function recognizeScreenshot(args, sender) {
  if (!validSender(sender)) throw new Error("Invalid OCR sender");
  if (active) throw new Error("本地识字正在运行，请稍后再试");
  if (
    !/^data:image\/png;base64,/.test(args?.image || "") ||
    args.image.length > 24000000 ||
    !["eng", "chi_sim", "eng+chi_sim"].includes(args.language) ||
    typeof args.job !== "string"
  )
    throw new Error("Invalid OCR input");
  const api = globalThis.chrome?.offscreen;
  if (!api) throw new Error("当前浏览器不支持本地 OCR 后台页面");
  const job = {
    tabId: sender.tab.id,
    documentId: sender.documentId,
    key: args.job,
  };
  active = job;
  let created = false;
  try {
    await api.createDocument({
      url: "screenshot.html",
      reasons: ["WORKERS"],
      justification:
        "Run bundled local OCR worker only for an explicitly requested screenshot",
    });
    created = true;
    if (active !== job || job.cancelled) throw new Error("已停止识字");
    return await browser.runtime.sendMessage({
      action: "charlieScreenshotOcrEngine",
      args,
    });
  } finally {
    if (created) await api.closeDocument().catch(() => undefined);
    if (active === job) active = null;
  }
}
export async function cancelScreenshotOcr(args, sender) {
  if (
    !validSender(sender) ||
    active?.tabId !== sender.tab.id ||
    active?.documentId !== sender.documentId ||
    active?.key !== args?.job
  )
    return;
  active.cancelled = true;
  await globalThis.chrome.offscreen.closeDocument().catch(() => undefined);
}
