import { browser } from "./browser";
import { hasSensitiveFields, isSensitivePage } from "./securityGuard";

export const CLIPBOARD_READ_PERMISSION = "clipboardRead";
const CLIPBOARD_READ_PERMISSIONS = {
  permissions: [CLIPBOARD_READ_PERMISSION],
};

export async function hasClipboardReadPermission() {
  try {
    return Boolean(
      await browser?.permissions?.contains?.(CLIPBOARD_READ_PERMISSIONS)
    );
  } catch {
    return false;
  }
}

export async function requestClipboardReadPermission() {
  try {
    return Boolean(
      await browser?.permissions?.request?.(CLIPBOARD_READ_PERMISSIONS)
    );
  } catch {
    return false;
  }
}

export async function readClipboardTextIfAllowed() {
  if (!(await hasClipboardReadPermission())) return null;

  try {
    // Popup settings are separate from content-script settings. Check the active
    // page here, before reading anything; unavailable page inspection fails closed.
    const [tab] = await browser.tabs.query({
      active: true,
      lastFocusedWindow: true,
    });
    if (
      !tab?.url ||
      !/^https?:/.test(tab.url) ||
      isSensitivePage(tab.url, null)
    )
      return null;
    const frames = await browser.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: hasSensitiveFields,
    });
    if (!frames?.length || frames.some(({ result }) => result !== false))
      return null;
    const [currentTab] = await browser.tabs.query({
      active: true,
      lastFocusedWindow: true,
    });
    if (currentTab?.id !== tab.id || currentTab?.url !== tab.url) return null;
    if (!navigator.clipboard?.readText) return null;
    const text = await navigator.clipboard.readText();
    const [afterRead] = await browser.tabs.query({
      active: true,
      lastFocusedWindow: true,
    });
    if (afterRead?.id !== tab.id || afterRead?.url !== tab.url) return null;
    return text;
  } catch {
    return null;
  }
}
