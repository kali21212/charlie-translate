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

import { genTransReq, parseTransRes } from "./trans";
import {
  DEFAULT_API_LIST,
  OPT_TRANS_MTRAN,
} from "../config";

describe("Charlie MTranServer integration", () => {
  const api = DEFAULT_API_LIST.find((item) => item.apiType === OPT_TRANS_MTRAN);

  test("ships a local-first /kiss preset without enabling it by default", () => {
    expect(api).toMatchObject({
      apiSlug: OPT_TRANS_MTRAN,
      apiName: OPT_TRANS_MTRAN,
      url: "http://localhost:8989/kiss",
      useBatchFetch: true,
      isDisabled: true,
    });
  });

  test("generates the MTranServer compatible batch request", async () => {
    const [url, init] = await genTransReq({
      ...api,
      key: "local-token",
      texts: ["Hello", "World"],
      from: "auto",
      to: "zh-CN",
      fromLang: "auto",
      toLang: "zh-CN",
    });

    expect(url).toBe("http://localhost:8989/kiss");
    expect(init.headers.Authorization).toBe("Bearer local-token");
    expect(JSON.parse(init.body)).toEqual({
      texts: ["Hello", "World"],
      from: "auto",
      to: "zh-CN",
    });
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
});
