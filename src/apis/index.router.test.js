jest.mock("query-string", () => ({
  stringify: (obj) => new URLSearchParams(obj).toString(),
}));

import {
  DEFAULT_API_LIST,
  OPT_TRANS_BUILTINAI,
  OPT_TRANS_CHARLIE_AUTO,
  OPT_TRANS_MTRAN,
  OPT_TRANS_OPENAI,
} from "../config";
import { apiTranslate } from "./index";
import { chromeTranslate } from "../libs/builtinAI";
import { getCacheDigest } from "../libs/cacheDigest";
import { handleTranslate } from "./trans";
import { getSetting } from "../libs/storage";
import * as browserCapability from "../libs/browser";
import { fetchData } from "../libs/fetch";

jest.mock("@streamparser/json", () => ({ JSONParser: jest.fn() }));
jest.mock("../libs/browser", () => ({
  __esModule: true,
  isBuiltinAIAvailable: true,
}));
jest.mock("../libs/builtinAI", () => ({
  chromeDetect: jest.fn(),
  chromeTranslate: jest.fn(),
}));
jest.mock("../libs/storage", () => ({
  getSetting: jest.fn(),
}));
jest.mock("../libs/cacheDigest", () => ({
  getCacheDigest: jest.fn(async () => "digest"),
}));
jest.mock("../libs/fetch", () => ({
  fetchData: jest.fn(),
}));
jest.mock("./trans", () => ({
  handleTranslate: jest.fn(),
  handleDetectLanguage: jest.fn(),
  handleDict: jest.fn(),
  handleGoogle: jest.fn(),
  handleGoogle2: jest.fn(),
  handleMicrosoft: jest.fn(),
  handleTencent: jest.fn(),
  handleDeeplFree: jest.fn(),
  handleYandexFree: jest.fn(),
  handleSubtitle: jest.fn(),
  buildSubtitleSystemPrompt: jest.fn(),
  formatIndexSubtitleEvents: jest.fn(),
  handleSummarize: jest.fn(),
}));
jest.mock("../libs/docInfo", () => ({
  getDocInfo: () => ({}),
}));
jest.mock("../libs/cache", () => ({
  getHttpCachePolyfill: jest.fn(),
  putHttpCachePolyfill: jest.fn(),
}));

const auto = DEFAULT_API_LIST.find(
  (api) => api.apiType === OPT_TRANS_CHARLIE_AUTO
);
const builtin = DEFAULT_API_LIST.find(
  (api) => api.apiType === OPT_TRANS_BUILTINAI
);
const mtran = {
  ...DEFAULT_API_LIST.find((api) => api.apiType === OPT_TRANS_MTRAN),
  useBatchFetch: false,
};
const translateWithRouter = () =>
  apiTranslate({
    text: "Hello",
    fromLang: "en",
    toLang: "zh-CN",
    apiSetting: auto,
    useCache: false,
    usePool: false,
  });

describe("Charlie Translation Router V2", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    browserCapability.isBuiltinAIAvailable = true;
    getCacheDigest.mockResolvedValue("digest");
  });

  test("prefers the browser-local Translator API", async () => {
    chromeTranslate.mockResolvedValue(["你好", "en", ""]);

    await expect(translateWithRouter()).resolves.toMatchObject({
      trText: "你好",
      routerEngine: OPT_TRANS_BUILTINAI,
    });
    expect(handleTranslate).not.toHaveBeenCalled();
  });

  test("falls back to Desktop MTranServer when browser-local translation fails", async () => {
    chromeTranslate.mockResolvedValue([
      "",
      "",
      "Translator unavailable for this language pair",
    ]);
    handleTranslate.mockImplementation(async function* (_texts, options) {
      expect(options.apiSetting.apiType).toBe(OPT_TRANS_MTRAN);
      yield { id: 0, result: ["桌面翻译", "en"] };
    });

    await expect(translateWithRouter()).resolves.toMatchObject({
      trText: "桌面翻译",
      routerEngine: OPT_TRANS_MTRAN,
    });
  });

  test("never falls through to a configured cloud provider", async () => {
    getSetting.mockResolvedValue({
      transApis: [
        { ...mtran, url: "https://remote.invalid/kiss", key: "fixture-token" },
        { apiType: OPT_TRANS_OPENAI, isDisabled: false },
      ],
    });
    chromeTranslate.mockResolvedValue(["", "", "local unavailable"]);
    handleTranslate.mockImplementation(async function* (_texts, options) {
      expect(options.apiSetting.apiType).toBe(OPT_TRANS_MTRAN);
      expect(options.apiSetting.url).toBe("http://127.0.0.1:8992/kiss");
      expect(options.apiSetting.key).toBeFalsy();
      throw new Error("desktop offline");
    });

    await expect(translateWithRouter()).rejects.toThrow("不会自动切换到云端");
    expect(handleTranslate).toHaveBeenCalledTimes(1);
    expect(
      handleTranslate.mock.calls.some(
        ([, options]) => options.apiSetting.apiType === OPT_TRANS_OPENAI
      )
    ).toBe(false);
  });

  test("uses Desktop directly when the browser has no local API", async () => {
    browserCapability.isBuiltinAIAvailable = false;
    handleTranslate.mockImplementation(async function* () {
      yield { id: 0, result: ["桌面翻译", "en"] };
    });
    await expect(translateWithRouter()).resolves.toMatchObject({
      routerEngine: OPT_TRANS_MTRAN,
    });
    expect(chromeTranslate).not.toHaveBeenCalled();
  });

  test("handles a thrown browser failure through the same local fallback", async () => {
    chromeTranslate.mockRejectedValue(new Error("browser API failed"));
    handleTranslate.mockImplementation(async function* () {
      yield { id: 0, result: ["桌面翻译", "en"] };
    });
    await expect(translateWithRouter()).resolves.toMatchObject({
      routerEngine: OPT_TRANS_MTRAN,
    });
  });

  test("does not start fallback or accept a result after cancellation", async () => {
    const controller = new AbortController();
    chromeTranslate.mockImplementation(async () => {
      controller.abort();
      return ["你好", "en", ""];
    });
    await expect(
      apiTranslate({
        text: "Hello",
        fromLang: "en",
        toLang: "zh-CN",
        apiSetting: auto,
        useCache: false,
        usePool: false,
        signal: controller.signal,
      })
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(handleTranslate).not.toHaveBeenCalled();
  });

  test("never uses a remote language detector inside CharlieAuto", async () => {
    getSetting.mockResolvedValue({ langDetector: "Baidu" });
    chromeTranslate.mockResolvedValue([
      "",
      "auto",
      "Automatic detection of source language failed: LanguageDetector unavailable",
    ]);
    handleTranslate.mockImplementation(async function* () {
      yield { id: 0, result: ["桌面翻译", "en"] };
    });
    await expect(
      apiTranslate({
        text: "Hello",
        fromLang: "auto",
        toLang: "zh-CN",
        apiSetting: auto,
        useCache: false,
        usePool: false,
      })
    ).resolves.toMatchObject({ routerEngine: OPT_TRANS_MTRAN });
    expect(fetchData).not.toHaveBeenCalled();
    expect(getSetting).not.toHaveBeenCalled();
  });
});
