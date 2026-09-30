import { captureScreenshot, saveScreenshot } from "./screenshotCapture";

function fixture() {
  const selection = {
    token: "document-1",
    region: { x: 1, y: 1, width: 10, height: 10 },
    width: 100,
    height: 100,
  };
  const browser = {
    runtime: {
      id: "extension",
      getURL: (path) => `chrome-extension://extension/${path}`,
    },
    tabs: {
      get: jest.fn().mockResolvedValue({
        id: 7,
        windowId: 2,
        url: "https://example.com/article",
      }),
      query: jest.fn().mockResolvedValue([{ id: 7 }]),
      sendMessage: jest.fn(async (_id, { action }) =>
        action === "charlieScreenshotSelect" ? selection : true
      ),
      captureVisibleTab: jest
        .fn()
        .mockResolvedValue("data:image/png;base64,test"),
    },
    windows: { get: jest.fn().mockResolvedValue({ focused: true }) },
    scripting: {
      executeScript: jest.fn().mockResolvedValue([{ result: false }]),
    },
  };
  const sender = {
    id: "extension",
    tab: { id: 7 },
    url: "https://example.com/article",
    frameId: 0,
  };
  return { browser, sender };
}
test("captures only the sender's verified active document and restores UI", async () => {
  const { browser, sender } = fixture();
  expect((await captureScreenshot(browser, sender)).image).toMatch(
    /^data:image/
  );
  expect(browser.tabs.captureVisibleTab).toHaveBeenCalledWith(2, {
    format: "png",
  });
  expect(browser.tabs.sendMessage).toHaveBeenLastCalledWith(
    7,
    { action: "charlieScreenshotShow", args: undefined },
    { frameId: 0 }
  );
});
test("rejects other extensions as capture callers", async () => {
  const { browser, sender } = fixture();
  sender.id = "another-extension";
  await expect(captureScreenshot(browser, sender)).rejects.toThrow("sender");
  expect(browser.tabs.captureVisibleTab).not.toHaveBeenCalled();
});
test("tab switch during selection cannot capture a different active tab", async () => {
  const { browser, sender } = fixture();
  browser.tabs.query
    .mockResolvedValueOnce([{ id: 7 }])
    .mockResolvedValue([{ id: 8 }]);
  await expect(captureScreenshot(browser, sender)).rejects.toThrow("状态检查");
  expect(browser.tabs.captureVisibleTab).not.toHaveBeenCalled();
});
test("navigation after capture discards bitmap", async () => {
  const { browser, sender } = fixture();
  browser.tabs.sendMessage.mockImplementation(async (_id, { action }) =>
    action === "charlieScreenshotSelect" ? { token: "doc", region: {} } : true
  );
  browser.tabs.get
    .mockResolvedValueOnce({
      id: 7,
      windowId: 2,
      url: "https://example.com/article",
    })
    .mockResolvedValueOnce({
      id: 7,
      windowId: 2,
      url: "https://example.com/article",
    })
    .mockResolvedValueOnce({
      id: 7,
      windowId: 2,
      url: "https://example.com/other",
    });
  await expect(captureScreenshot(browser, sender)).rejects.toThrow("已丢弃");
});
test("sensitive frame fields fail closed", async () => {
  const { browser, sender } = fixture();
  browser.scripting.executeScript.mockResolvedValue([
    { result: false },
    { result: true },
  ]);
  await expect(captureScreenshot(browser, sender)).rejects.toThrow("敏感字段");
  expect(browser.tabs.captureVisibleTab).not.toHaveBeenCalled();
});

test("save only downloads a validated PNG from the extension content script", async () => {
  const { browser, sender } = fixture();
  browser.downloads = { download: jest.fn().mockResolvedValue(12) };
  expect(
    await saveScreenshot(browser, sender, "data:image/png;base64,dGVzdA==")
  ).toBe(12);
  expect(browser.downloads.download).toHaveBeenCalledWith({
    url: "data:image/png;base64,dGVzdA==",
    filename: "Charlie-screenshot.png",
    saveAs: false,
  });
  await expect(
    saveScreenshot(browser, sender, "https://example.com/file")
  ).rejects.toThrow("image");
  await expect(
    saveScreenshot(
      browser,
      { ...sender, frameId: 1 },
      "data:image/png;base64,dGVzdA=="
    )
  ).rejects.toThrow("sender");
  expect(browser.downloads.download).toHaveBeenCalledTimes(1);
});
test("moving the selected tab to another window prevents capture", async () => {
  const { browser, sender } = fixture();
  browser.tabs.get
    .mockResolvedValueOnce({
      id: 7,
      windowId: 2,
      url: "https://example.com/article",
    })
    .mockResolvedValue({
      id: 7,
      windowId: 3,
      url: "https://example.com/article",
    });
  await expect(captureScreenshot(browser, sender)).rejects.toThrow("变化");
  expect(browser.tabs.captureVisibleTab).not.toHaveBeenCalled();
});
