import browser from "webextension-polyfill";
import { recognizeLocalScreenshot } from "./screenshotLocalOcr";
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
    typeof args?.image !== "string" ||
    !/^data:image\/png;base64,[A-Za-z0-9+/]+=*$/.test(args.image) ||
    args.image.length > 24000000 ||
    typeof args.job !== "string" ||
    args.job.length > 100
  )
    throw new Error("Invalid OCR input");
  const job = {
    tabId: sender.tab.id,
    documentId: sender.documentId,
    key: args.job,
    controller: new AbortController(),
  };
  active = job;
  try {
    const result = await recognizeLocalScreenshot(
      args.image,
      job.controller.signal
    );
    if (job.controller.signal.aborted) throw new Error("已停止识字");
    return result;
  } finally {
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
  active.controller.abort();
}
