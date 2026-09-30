/* eslint-disable testing-library/no-container, testing-library/no-unnecessary-act */
import { act } from "react";
import { createRoot } from "react-dom/client";
import browser from "webextension-polyfill";
import Screenshot from "./index";
import { getSettingWithDefault } from "../../libs/storage";
import { handleTranslate } from "../../apis/trans";

jest.mock("webextension-polyfill", () => ({ runtime: { sendMessage: jest.fn() } }));
jest.mock("../../libs/storage", () => ({
  getSettingWithDefault: jest.fn().mockResolvedValue({
    transApis: [{ apiSlug: "local", apiType: "MTranServer", apiName: "MTranServer" }],
    tranboxSetting: { apiSlugs: ["local"], toLang: "zh-CN" },
  }),
}));
jest.mock("../../apis/trans", () => ({ handleTranslate: jest.fn() }));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const png = "data:image/png;base64,dGVzdA==";
const OriginalImage = globalThis.Image;
let host, root;
const button = (name) => [...host.querySelectorAll("button")].find((b) => b.textContent === name);
const click = async (name) => act(async () => { button(name).click(); });

beforeEach(() => {
  getSettingWithDefault.mockResolvedValue({
    transApis: [{ apiSlug: "local", apiType: "MTranServer", apiName: "MTranServer" }],
    tranboxSetting: { apiSlugs: ["local"], toLang: "zh-CN" },
  });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  handleTranslate.mockReset().mockImplementation(async function* () { yield { result: ["你好"] }; });
  browser.runtime.sendMessage.mockReset().mockImplementation(async ({ action }) =>
    action === "charlieScreenshotCapture"
      ? { image: png, width: 100, height: 100, region: { x: 0, y: 0, width: 20, height: 20 } }
      : { text: "Hello", engine: "RapidOCR" }
  );
  jest.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: jest.fn() });
  jest.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue(png);
  globalThis.Image = class {
    constructor() { this.naturalWidth = 100; this.naturalHeight = 100; }
    async decode() {}
  };
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  globalThis.Image = OriginalImage;
  jest.restoreAllMocks();
});
async function open() { await act(async () => root.render(<Screenshot />)); }

test("screenshot translate performs capture OCR and translation in one action", async () => {
  await open();
  expect(button("截图翻译")).not.toBeUndefined();
  expect(button("保存截图")).toBeUndefined();
  expect(button("复制截图")).toBeUndefined();
  await click("截图翻译");
  expect(host.querySelectorAll("textarea")[0].value).toBe("Hello");
  expect(host.querySelectorAll("textarea")[1].value).toBe("你好");
  expect(handleTranslate).toHaveBeenCalledTimes(1);
});

test("stopping screenshot OCR discards a late result", async () => {
  await open();
  let finish;
  browser.runtime.sendMessage.mockImplementation(({ action }) =>
    action === "charlieScreenshotCapture"
      ? Promise.resolve({ image: png, width: 100, height: 100, region: { x: 0, y: 0, width: 20, height: 20 } })
      : new Promise((resolve) => { finish = resolve; })
  );
  await click("截图翻译");
  await click("停止");
  await act(async () => finish({ text: "late secret" }));
  expect(host.querySelectorAll("textarea")[0].value).toBe("");
  expect(button("截图翻译").disabled).toBe(false);
});
