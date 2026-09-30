/* eslint-disable testing-library/no-container, testing-library/no-unnecessary-act */
import { act } from "react";
import { createRoot } from "react-dom/client";
import browser from "webextension-polyfill";
import Screenshot from "./index";
import { getSettingWithDefault } from "../../libs/storage";
import { handleTranslate } from "../../apis/trans";
jest.mock("webextension-polyfill", () => ({
  runtime: { sendMessage: jest.fn() },
}));
jest.mock("../../libs/storage", () => ({
  getSettingWithDefault: jest.fn().mockResolvedValue({
    transApis: [
      { apiSlug: "local", apiType: "MTranServer", apiName: "MTranServer" },
    ],
    tranboxSetting: { apiSlugs: ["local"], toLang: "zh-CN" },
  }),
}));
jest.mock("../../apis/trans", () => ({ handleTranslate: jest.fn() }));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const png = "data:image/png;base64,dGVzdA==";
const OriginalImage = globalThis.Image;
let host, root;
const button = (name) =>
  [...host.querySelectorAll("button")].find((b) => b.textContent === name);
const click = async (name) =>
  act(async () => {
    button(name).click();
  });
beforeEach(() => {
  getSettingWithDefault.mockResolvedValue({
    transApis: [
      { apiSlug: "local", apiType: "MTranServer", apiName: "MTranServer" },
    ],
    tranboxSetting: { apiSlugs: ["local"], toLang: "zh-CN" },
  });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  handleTranslate.mockReset().mockImplementation(async function* () {
    yield { result: ["你好"] };
  });
  browser.runtime.sendMessage
    .mockReset()
    .mockImplementation(async ({ action }) =>
      action === "charlieScreenshotCapture"
        ? {
            image: png,
            width: 100,
            height: 100,
            region: { x: 0, y: 0, width: 20, height: 20 },
          }
        : { text: "Hello" }
    );
  jest
    .spyOn(HTMLCanvasElement.prototype, "getContext")
    .mockReturnValue({ drawImage: jest.fn() });
  jest.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue(png);
  globalThis.Image = class {
    constructor() {
      this.naturalWidth = 100;
      this.naturalHeight = 100;
    }
    async decode() {}
  };
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  globalThis.Image = OriginalImage;
  delete window.showSaveFilePicker;
  jest.restoreAllMocks();
});
async function open() {
  await act(async () => root.render(<Screenshot />));
}
test("opening the tool and recognizing text never translates automatically", async () => {
  await open();
  expect(browser.runtime.sendMessage).not.toHaveBeenCalled();
  await click("框选截图");
  expect(host.querySelector("img")).not.toBeNull();
  await click("本地识字");
  expect(host.querySelectorAll("textarea")[0].value).toBe("Hello");
  expect(handleTranslate).not.toHaveBeenCalled();
  await click("翻译");
  expect(host.querySelectorAll("textarea")[1].value).toBe("你好");
});
test("stopping OCR discards a late result and unlocks the controls", async () => {
  await open();
  await click("框选截图");
  let finish;
  browser.runtime.sendMessage.mockImplementation(({ action }) =>
    action === "charlieScreenshotOcr"
      ? new Promise((resolve) => {
          finish = resolve;
        })
      : Promise.resolve()
  );
  await click("本地识字");
  await click("停止");
  await act(async () => finish({ text: "late secret" }));
  expect(host.querySelectorAll("textarea")[0].value).toBe("");
  expect(button("框选截图").disabled).toBe(false);
});
test("save cancellation is reported as cancellation rather than success", async () => {
  await open();
  await click("框选截图");
  window.showSaveFilePicker = jest
    .fn()
    .mockRejectedValue(new DOMException("Canceled", "AbortError"));
  await click("保存截图");
  expect(host.querySelector('[role="status"]').textContent).toMatch("取消");
});
