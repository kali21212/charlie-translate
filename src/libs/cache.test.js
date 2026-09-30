jest.mock("../config", () => ({
  CACHE_NAME: "owned-cache",
  DEFAULT_CACHE_TIMEOUT: 604800,
}));
jest.mock("./client", () => ({ isExt: false }));
jest.mock("./browser", () => ({ isBg: () => false }));
jest.mock("./msg", () => ({ sendBgMsg: jest.fn() }));
jest.mock("./log", () => ({ kissLog: jest.fn() }));
jest.mock("./response", () => ({
  parseResponse: async (response) => JSON.parse(response.body),
}));

import { getHttpCache, putHttpCache, pruneExpiredCaches } from "./cache";

describe("translation cache retention", () => {
  let entries;
  beforeEach(() => {
    entries = new Map();
    global.Request = class {
      constructor(url, init = {}) {
        this.url = url;
        this.method = init.method || "GET";
        this.body = init.body;
      }
      async text() {
        return this.body;
      }
    };
    global.Response = class {
      constructor(body, init) {
        this.body = body;
        this.headers = { get: (name) => init.headers[name] ?? null };
      }
    };
    const cache = {
      keys: async () => [...entries.keys()].map((url) => new Request(url)),
      match: async (request) => entries.get(request.url),
      put: async (request, response) => entries.set(request.url, response),
      delete: jest.fn(async (request) => entries.delete(request.url)),
    };
    global.caches = { has: async () => true, open: async () => cache };
  });

  test("keeps recent responses, deletes old and unversioned entries from disk", async () => {
    entries.set(
      "http://127.0.0.1/old",
      new Response("{}", {
        headers: {
          "X-Charlie-Cached-At": String(Date.now() - 8 * 86400000),
          "Cache-Control": "max-age=604800",
        },
      })
    );
    entries.set(
      "http://127.0.0.1/legacy",
      new Response("{}", { headers: { "Cache-Control": "max-age=604800" } })
    );
    await putHttpCache({
      input: "http://127.0.0.1/recent",
      data: { text: "recent" },
    });
    await pruneExpiredCaches();
    expect([...entries.keys()]).toEqual(["http://127.0.0.1/recent"]);
    await expect(
      getHttpCache({ input: "http://127.0.0.1/recent" })
    ).resolves.toEqual({ text: "recent" });
  });

  test("never returns expired responses even between sweeps", async () => {
    await pruneExpiredCaches();
    entries.set(
      "http://127.0.0.1/expired",
      new Response("{}", {
        headers: {
          "X-Charlie-Cached-At": String(Date.now() - 2000),
          "Cache-Control": "max-age=1",
        },
      })
    );
    await expect(
      getHttpCache({ input: "http://127.0.0.1/expired" })
    ).resolves.toBeNull();
    expect(entries.size).toBe(0);
  });
});
