import { browser } from "./browser";
import {
  hasClipboardReadPermission,
  readClipboardTextIfAllowed,
  requestClipboardReadPermission,
} from "./clipboard";

jest.mock("./browser", () => ({
  browser: {
    tabs: { query: jest.fn() },
    scripting: { executeScript: jest.fn() },
    permissions: {
      contains: jest.fn(),
      request: jest.fn(),
    },
  },
}));

describe("clipboard permissions", () => {
  beforeEach(() => {
    browser.tabs.query
      .mockReset()
      .mockResolvedValue([{ id: 1, url: "https://example.com/docs" }]);
    browser.scripting.executeScript
      .mockReset()
      .mockResolvedValue([{ result: false }]);
    browser.permissions.contains.mockReset();
    browser.permissions.request.mockReset();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { readText: jest.fn() },
    });
  });

  test("checks and requests the optional clipboardRead permission", async () => {
    browser.permissions.contains.mockResolvedValue(true);
    browser.permissions.request.mockResolvedValue(true);

    await expect(hasClipboardReadPermission()).resolves.toBe(true);
    await expect(requestClipboardReadPermission()).resolves.toBe(true);
    expect(browser.permissions.contains).toHaveBeenCalledWith({
      permissions: ["clipboardRead"],
    });
    expect(browser.permissions.request).toHaveBeenCalledWith({
      permissions: ["clipboardRead"],
    });
  });

  test("reads text only after permission has been granted", async () => {
    browser.permissions.contains.mockResolvedValue(true);
    navigator.clipboard.readText.mockResolvedValue("clipboard text");

    await expect(readClipboardTextIfAllowed()).resolves.toBe("clipboard text");

    browser.permissions.contains.mockResolvedValue(false);
    await expect(readClipboardTextIfAllowed()).resolves.toBeNull();
    expect(navigator.clipboard.readText).toHaveBeenCalledTimes(1);
  });

  test("fails closed when permission or clipboard APIs reject", async () => {
    browser.permissions.contains.mockRejectedValue(new Error("unavailable"));
    await expect(hasClipboardReadPermission()).resolves.toBe(false);

    browser.permissions.request.mockRejectedValue(new Error("denied"));
    await expect(requestClipboardReadPermission()).resolves.toBe(false);

    browser.permissions.contains.mockResolvedValue(true);
    navigator.clipboard.readText.mockRejectedValue(new Error("blocked"));
    await expect(readClipboardTextIfAllowed()).resolves.toBeNull();
  });

  test.each([
    "https://github.com/settings/security",
    "https://example.com/#/login",
    "chrome://extensions",
    undefined,
  ])("does not read clipboard on blocked or unknown page %s", async (url) => {
    browser.permissions.contains.mockResolvedValue(true);
    browser.tabs.query.mockResolvedValue([{ id: 1, url }]);
    await expect(readClipboardTextIfAllowed()).resolves.toBeNull();
    expect(navigator.clipboard.readText).not.toHaveBeenCalled();
  });

  test.each(
    [[{ result: true }], [{ result: false }, { result: true }], [], [{}]].map(
      (frames) => [frames]
    )
  )("blocks secret fields and unknown frame results", async (frames) => {
    browser.permissions.contains.mockResolvedValue(true);
    browser.scripting.executeScript.mockResolvedValue(frames);
    await expect(readClipboardTextIfAllowed()).resolves.toBeNull();
    expect(navigator.clipboard.readText).not.toHaveBeenCalled();
  });

  test("fails closed on inspection errors and navigation races", async () => {
    browser.permissions.contains.mockResolvedValue(true);
    browser.scripting.executeScript.mockRejectedValueOnce(
      new Error("restricted tab")
    );
    await expect(readClipboardTextIfAllowed()).resolves.toBeNull();
    browser.tabs.query
      .mockResolvedValueOnce([{ id: 1, url: "https://example.com/docs" }])
      .mockResolvedValueOnce([{ id: 1, url: "https://example.com/login" }]);
    await expect(readClipboardTextIfAllowed()).resolves.toBeNull();
    expect(navigator.clipboard.readText).not.toHaveBeenCalled();
  });

  test("discards clipboard text if navigation happens during the read", async () => {
    browser.permissions.contains.mockResolvedValue(true);
    navigator.clipboard.readText.mockResolvedValue("secret");
    browser.tabs.query
      .mockResolvedValueOnce([{ id: 1, url: "https://example.com/docs" }])
      .mockResolvedValueOnce([{ id: 1, url: "https://example.com/docs" }])
      .mockResolvedValueOnce([{ id: 1, url: "https://example.com/login" }]);
    await expect(readClipboardTextIfAllowed()).resolves.toBeNull();
  });
});
