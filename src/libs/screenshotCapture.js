import { isSensitivePage, hasSensitiveFields } from "./securityGuard";

export const SCREENSHOT_CAPTURE = "charlieScreenshotCapture";
export const SCREENSHOT_SELECT = "charlieScreenshotSelect";
export const SCREENSHOT_VERIFY = "charlieScreenshotVerify";
export const SCREENSHOT_SHOW = "charlieScreenshotShow";

// Never accept a tab/window ID supplied by the front-end. Bind to its sender.
export async function captureScreenshot(browser, sender) {
  if (
    sender?.id !== browser.runtime.id ||
    !/^https?:\/\//.test(sender?.url || "") ||
    sender?.frameId !== 0 ||
    !Number.isInteger(sender?.tab?.id)
  )
    throw new Error("Invalid screenshot sender");
  const tabId = sender.tab.id;
  const send = (action, args) =>
    browser.tabs.sendMessage(tabId, { action, args }, { frameId: 0 });
  const checkTab = async () => {
    const tab = await browser.tabs.get(tabId);
    const [active] = await browser.tabs.query({
      active: true,
      windowId: tab.windowId,
    });
    if (
      active?.id !== tabId ||
      !/^https?:\/\//.test(tab.url || "") ||
      tab.pendingUrl ||
      isSensitivePage(tab.url, null)
    )
      throw new Error(
        `页面状态检查未通过：活动标签 ${active?.id}，目标标签 ${tabId}，页面跳转 ${Boolean(tab.pendingUrl)}，敏感地址 ${isSensitivePage(tab.url, null)}`
      );
    const frames = await browser.scripting.executeScript({
      target: { tabId, allFrames: true },
      func: hasSensitiveFields,
    });
    if (!frames?.length || frames.some((frame) => frame.result !== false))
      throw new Error("页面含敏感字段或无法完成隐私检查，已禁止截图");
    return tab;
  };
  try {
    const initial = await checkTab();
    const selection = await send(SCREENSHOT_SELECT);
    if (!selection?.token || !selection?.region) throw new Error("已取消截图");
    const before = await checkTab();
    if (
      initial.url !== before.url ||
      initial.windowId !== before.windowId ||
      !(await send(SCREENSHOT_VERIFY, selection))
    )
      throw new Error("页面发生变化，请重新截图");
    const image = await browser.tabs.captureVisibleTab(before.windowId, {
      format: "png",
    });
    const after = await checkTab();
    if (
      before.url !== after.url ||
      before.windowId !== after.windowId ||
      !(await send(SCREENSHOT_VERIFY, selection))
    )
      throw new Error("截图期间页面发生变化，结果已丢弃");
    return { ...selection, image };
  } finally {
    await send(SCREENSHOT_SHOW).catch(() => undefined);
  }
}

export async function saveScreenshot(browser, sender, image) {
  if (
    sender?.id !== browser.runtime.id ||
    sender.frameId !== 0 ||
    !Number.isInteger(sender.tab?.id) ||
    !/^https?:\/\//.test(sender.url || "")
  )
    throw new Error("Invalid screenshot sender");
  if (
    typeof image !== "string" ||
    image.length > 24000000 ||
    !/^data:image\/png;base64,[A-Za-z0-9+/]+=*$/.test(image)
  )
    throw new Error("Invalid screenshot image");
  return browser.downloads.download({
    url: image,
    filename: "Charlie-screenshot.png",
    saveAs: false,
  });
}
