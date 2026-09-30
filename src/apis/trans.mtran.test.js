import { genTransReq, handleTranslate, parseTransRes } from "./trans";
import { DEFAULT_API_LIST, OPT_TRANS_MTRAN } from "../config";
import { fetchData } from "../libs/fetch";

jest.mock("query-string", () => ({
  stringify: (obj) => new URLSearchParams(obj).toString(),
}));

jest.mock("@streamparser/json", () =>
  jest.requireActual("../../node_modules/@streamparser/json/dist/cjs/index.js")
);

const { TextDecoder, TextEncoder } = require("util");
global.TextEncoder = global.TextEncoder || TextEncoder;
global.TextDecoder = global.TextDecoder || TextDecoder;

jest.mock("../libs/fetch", () => ({
  fetchData: jest.fn(),
  fetchStream: jest.fn(),
}));

jest.mock("../libs/docInfo", () => ({
  getDocInfo: () => ({}),
}));

describe("Charlie MTranServer integration", () => {
  const api = DEFAULT_API_LIST.find((item) => item.apiType === OPT_TRANS_MTRAN);

  test("ships an enabled local-first /kiss preset", () => {
    expect(api).toMatchObject({
      apiSlug: OPT_TRANS_MTRAN,
      apiName: OPT_TRANS_MTRAN,
      url: "http://127.0.0.1:8992/kiss",
      useBatchFetch: true,
      isDisabled: false,
    });
  });

  test.each(["http://127.0.0.1:8989/kiss", "http://[::1]:8989/kiss"])(
    "supports custom loopback endpoint %s without sending an empty bearer token",
    async (url) => {
      const [, init] = await genTransReq({
        ...api,
        url,
        texts: ["Hello"],
        fromLang: "en",
        toLang: "zh-CN",
      });
      expect(init.headers.Authorization).toBeUndefined();
    }
  );

  test.each([
    "https://example.com/kiss",
    "http://localhost.evil.test/kiss",
    "http://user:secret@localhost:8989/kiss",
    "ftp://localhost/kiss",
  ])("rejects nonlocal/credential URL %s before sending text", async (url) => {
    await expect(
      genTransReq({
        ...api,
        url,
        texts: ["private"],
        fromLang: "en",
        toLang: "zh-CN",
      })
    ).rejects.toThrow("loopback URL");
  });

  test("desktop bridge adds its local-only header and supports single-text responses", async () => {
    const [, init] = await genTransReq({
      ...api,
      useBatchFetch: false,
      texts: ["Hello"],
      fromLang: "en",
      toLang: "zh-CN",
    });
    expect(init.headers["X-Charlie-Translate"]).toBe("desktop-v1");
    expect(init.headers.Authorization).toBeUndefined();
    expect(JSON.parse(init.body)).toEqual({
      text: "Hello",
      from: "en",
      to: "zh-CN",
    });
    await expect(
      parseTransRes(
        { text: "你好", src: "en" },
        { ...api, useBatchFetch: false }
      )
    ).resolves.toEqual([["你好", "en"]]);
  });

  test("generates the MTranServer compatible batch request", async () => {
    const [url, init] = await genTransReq({
      ...api,
      texts: ["Hello", "World"],
      from: "auto",
      to: "zh-CN",
      fromLang: "auto",
      toLang: "zh-CN",
    });

    expect(url).toBe("http://127.0.0.1:8992/kiss");
    expect(init.redirect).toBe("error");
    expect(init.credentials).toBe("omit");
    expect(init.headers.Authorization).toBeUndefined();
    expect(init.headers["X-Charlie-Translate"]).toBe("desktop-v1");
    expect(JSON.parse(init.body)).toEqual({
      texts: ["Hello", "World"],
      from: "auto",
      to: "zh-CN",
    });
  });

  test("explains that Desktop EXE must be open when bridge is unavailable", async () => {
    fetchData.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const run = async () => {
      for await (const _chunk of handleTranslate(["Hello"], {
        from: "auto",
        to: "zh-CN",
        fromLang: "auto",
        toLang: "zh-CN",
        apiSetting: api,
        usePool: false,
      })) {
        // no-op
      }
    };
    await expect(run()).rejects.toThrow("请先打开 CharlieTranslate.exe");
  });

  test("parses MTranServer compatible batch responses", async () => {
    const result = await parseTransRes(
      {
        translations: [
          { text: "你好", src: "en" },
          { text: "世界", src: "en" },
        ],
      },
      {
        apiType: OPT_TRANS_MTRAN,
        texts: ["Hello", "World"],
        useBatchFetch: true,
      }
    );

    expect(result).toEqual([
      ["你好", "en"],
      ["世界", "en"],
    ]);
  });

  test("request hooks cannot redirect local text to a remote service", async () => {
    await expect(
      genTransReq({
        ...api,
        texts: ["private"],
        fromLang: "en",
        toLang: "zh-CN",
        reqHook:
          '(_args, req) => ({ ...req, url: "https://example.com/kiss" })',
      })
    ).rejects.toThrow("loopback URL");
  });

  test.each([{}, { translations: [] }, { translations: [{}] }])(
    "rejects missing or malformed batch output",
    async (res) => {
      await expect(
        parseTransRes(res, { ...api, texts: ["Hello"] })
      ).rejects.toThrow("Invalid MTranServer batch response");
    }
  );
});
