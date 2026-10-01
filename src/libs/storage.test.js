import {
  STOKEY_SETTING,
  STOKEY_RULES,
  STOKEY_SETTING_BACKUP_V1_BEFORE_V2,
  SETTINGS_VERSION_V2,
  SETTINGS_VERSION_V3,
  DEFAULT_SUBTITLE_SETTING,
  DEFAULT_API_LIST,
  OPT_TRANS_CHARLIE_AUTO,
  OPT_TRANS_DEEPSEEK,
  OPT_TRANS_MICROSOFT,
  OPT_TRANS_MTRAN,
  OPT_TRANS_OPENAI,
  OPT_TRANS_TENCENT,
} from "../config";
import { getSettingWithDefault, runDataMigration } from "./storage";

// 存储测试不涉及流式解析，隔离 ESM-only 依赖以免 Jest 27 在加载阶段失败。
jest.mock("@streamparser/json", () => ({ JSONParser: jest.fn() }));
// jsdom 并非扩展页面，使用空实现避免 webextension-polyfill 在模块初始化时主动抛错。
jest.mock("webextension-polyfill", () => ({}));

const readStoredJson = (key) => JSON.parse(window.localStorage.getItem(key));

function loadGmStorageModule() {
  let storageModule;
  jest.isolateModules(() => {
    jest.doMock("./client", () => ({
      isExt: false,
      isGm: true,
    }));
    storageModule = require("./storage");
  });
  jest.dontMock("./client");
  return storageModule;
}

describe("settings storage migration", () => {
  test("migrates legacy no-key loopback endpoints while preserving explicit providers", async () => {
    window.localStorage.setItem(
      STOKEY_SETTING,
      JSON.stringify({
        transApis: [
          {
            apiType: OPT_TRANS_MTRAN,
            apiSlug: "legacy",
            url: "http://localhost:8989/kiss",
          },
          {
            apiType: OPT_TRANS_MTRAN,
            apiSlug: "keyed",
            url: "http://127.0.0.1:8989/kiss",
            key: "chosen-key",
          },
          {
            apiType: OPT_TRANS_MTRAN,
            apiSlug: "custom",
            url: "http://127.0.0.1:9999/kiss",
          },
        ],
      })
    );
    const setting = await getSettingWithDefault();
    expect(
      setting.transApis
        .filter((api) => api.apiType === OPT_TRANS_MTRAN)
        .map((api) => api.url)
    ).toEqual([
      "http://127.0.0.1:8992/kiss",
      "http://127.0.0.1:8989/kiss",
      "http://127.0.0.1:9999/kiss",
    ]);
    expect(
      setting.transApis.some((api) => api.apiType === OPT_TRANS_CHARLIE_AUTO)
    ).toBe(true);
  });
  beforeEach(() => {
    window.localStorage.clear();
    delete window.KISS_GM;
    delete globalThis.GM;
    delete globalThis.GM_setValue;
    delete globalThis.GM_getValue;
    delete globalThis.GM_deleteValue;
  });

  afterEach(() => {
    delete globalThis.GM;
    delete globalThis.GM_setValue;
    delete globalThis.GM_getValue;
    delete globalThis.GM_deleteValue;
  });

  test("migrates only the old global MTran default to Translation Router V2", async () => {
    window.localStorage.setItem(
      STOKEY_SETTING,
      JSON.stringify({
        version: SETTINGS_VERSION_V3,
        inputRule: { apiSlug: OPT_TRANS_MTRAN },
        tranboxSetting: { apiSlugs: [OPT_TRANS_MTRAN] },
        subtitleSetting: { apiSlug: OPT_TRANS_MTRAN },
        transApis: [
          DEFAULT_API_LIST.find((api) => api.apiType === OPT_TRANS_MTRAN),
        ],
      })
    );
    window.localStorage.setItem(
      STOKEY_RULES,
      JSON.stringify([
        { pattern: "*", apiSlug: OPT_TRANS_MTRAN },
        { pattern: "example.com", apiSlug: OPT_TRANS_MTRAN },
      ])
    );

    await expect(runDataMigration()).resolves.toBe(true);

    const setting = readStoredJson(STOKEY_SETTING);
    expect(setting.translationRouterVersion).toBe(2);
    expect(setting.inputRule.apiSlug).toBe(OPT_TRANS_CHARLIE_AUTO);
    expect(setting.tranboxSetting.apiSlugs).toEqual([OPT_TRANS_CHARLIE_AUTO]);
    expect(setting.subtitleSetting.apiSlug).toBe(OPT_TRANS_CHARLIE_AUTO);
    expect(
      setting.transApis.some((api) => api.apiType === OPT_TRANS_CHARLIE_AUTO)
    ).toBe(true);

    const rules = readStoredJson(STOKEY_RULES);
    expect(rules[0].apiSlug).toBe(OPT_TRANS_CHARLIE_AUTO);
    expect(rules[1].apiSlug).toBe(OPT_TRANS_MTRAN);
  });

  test("normalizes legacy routing before the install migration is persisted", async () => {
    window.localStorage.setItem(
      STOKEY_SETTING,
      JSON.stringify({
        version: SETTINGS_VERSION_V3,
        inputRule: { apiSlug: OPT_TRANS_MTRAN },
        tranboxSetting: { apiSlugs: [OPT_TRANS_MTRAN] },
        subtitleSetting: { apiSlug: OPT_TRANS_MTRAN },
      })
    );
    const setting = await getSettingWithDefault();
    expect(setting.inputRule.apiSlug).toBe(OPT_TRANS_CHARLIE_AUTO);
    expect(setting.tranboxSetting.apiSlugs).toEqual([OPT_TRANS_CHARLIE_AUTO]);
    expect(setting.subtitleSetting.apiSlug).toBe(OPT_TRANS_CHARLIE_AUTO);
  });

  test.each([
    { url: "http://127.0.0.1:9999/kiss", key: "" },
    { url: "http://127.0.0.1:8992/kiss", key: "fixture-key" },
  ])(
    "preserves explicit MTran endpoint/token selections: %p",
    async (config) => {
      const provider = {
        ...DEFAULT_API_LIST.find((api) => api.apiType === OPT_TRANS_MTRAN),
        ...config,
      };
      const setting = {
        version: SETTINGS_VERSION_V3,
        inputRule: { apiSlug: OPT_TRANS_MTRAN },
        tranboxSetting: { apiSlugs: [OPT_TRANS_MTRAN] },
        subtitleSetting: { apiSlug: OPT_TRANS_MTRAN },
        transApis: [
          provider,
          { apiType: "OpenAI", apiSlug: "chosen-cloud", isDisabled: false },
        ],
      };
      window.localStorage.setItem(STOKEY_SETTING, JSON.stringify(setting));
      const rules = [{ pattern: "*", apiSlug: OPT_TRANS_MTRAN }];
      window.localStorage.setItem(STOKEY_RULES, JSON.stringify(rules));
      await expect(runDataMigration()).resolves.toBe(true);
      const stored = readStoredJson(STOKEY_SETTING);
      expect(stored.inputRule).toEqual(setting.inputRule);
      expect(stored.tranboxSetting).toEqual(setting.tranboxSetting);
      expect(stored.subtitleSetting).toEqual(setting.subtitleSetting);
      expect(stored.transApis).toEqual(
        expect.arrayContaining(setting.transApis)
      );
      expect(readStoredJson(STOKEY_RULES)).toEqual(rules);
    }
  );

  test("rolls back settings if the companion rule migration cannot commit", async () => {
    const oldSetting = {
      version: SETTINGS_VERSION_V3,
      inputRule: { apiSlug: OPT_TRANS_MTRAN },
    };
    const oldRules = [{ pattern: "*", apiSlug: OPT_TRANS_MTRAN }];
    window.localStorage.setItem(STOKEY_SETTING, JSON.stringify(oldSetting));
    window.localStorage.setItem(STOKEY_RULES, JSON.stringify(oldRules));
    const nativeSetItem = window.Storage.prototype.setItem;
    let failed = false;
    const setItem = jest
      .spyOn(window.Storage.prototype, "setItem")
      .mockImplementation(function (key, value) {
        if (key === STOKEY_RULES && !failed) {
          failed = true;
          throw new Error("fixture rule write failure");
        }
        return nativeSetItem.call(this, key, value);
      });
    try {
      await expect(runDataMigration()).resolves.toBe(false);
      expect(readStoredJson(STOKEY_SETTING)).toEqual(oldSetting);
      expect(readStoredJson(STOKEY_RULES)).toEqual(oldRules);
    } finally {
      setItem.mockRestore();
    }
    await expect(runDataMigration()).resolves.toBe(true);
    expect(readStoredJson(STOKEY_RULES)[0].apiSlug).toBe(
      OPT_TRANS_CHARLIE_AUTO
    );
  });

  test("runDataMigration backs up raw v1 settings and stores current settings", async () => {
    const oldSetting = {
      uiLang: "zh-CN",
      transApis: [
        {
          apiSlug: "openai",
          apiName: "OpenAI",
          systemPrompt: "custom batch prompt",
        },
      ],
    };
    window.localStorage.setItem(STOKEY_SETTING, JSON.stringify(oldSetting));

    await runDataMigration();

    const backup = readStoredJson(STOKEY_SETTING_BACKUP_V1_BEFORE_V2);
    const stored = readStoredJson(STOKEY_SETTING);

    expect(backup).toEqual(oldSetting);
    expect(stored.version).toBe(SETTINGS_VERSION_V3);
    expect(stored.translationRouterVersion).toBe(2);
    const migratedOpenAI = stored.transApis.find(
      (api) => api.apiSlug === "openai"
    );
    expect(migratedOpenAI.batchPromptSlug).toMatch(/^prompt_migrated_batch_/);
    expect(migratedOpenAI).not.toHaveProperty("systemPrompt");
  });

  test.each([
    [true, "dark"],
    [false, "light"],
  ])(
    "migrates boolean theme %p without changing current settings",
    async (darkMode, expected) => {
      const oldSetting = {
        version: SETTINGS_VERSION_V3,
        darkMode,
        uiLang: "en",
      };
      window.localStorage.setItem(STOKEY_SETTING, JSON.stringify(oldSetting));

      await runDataMigration();

      const stored = readStoredJson(STOKEY_SETTING);
      expect(stored).toMatchObject({
        ...oldSetting,
        darkMode: expected,
        translationRouterVersion: 2,
      });
      expect(
        stored.transApis.some((api) => api.apiType === OPT_TRANS_CHARLIE_AUTO)
      ).toBe(true);
      expect(readStoredJson(STOKEY_SETTING_BACKUP_V1_BEFORE_V2)).toBe(null);
    }
  );

  test("finishes schema and theme migration in one settings write", async () => {
    const oldSetting = { version: SETTINGS_VERSION_V2, darkMode: true };
    window.localStorage.setItem(STOKEY_SETTING, JSON.stringify(oldSetting));
    const setItem = jest.spyOn(window.Storage.prototype, "setItem");
    try {
      await runDataMigration();

      expect(readStoredJson(STOKEY_SETTING)).toMatchObject({
        version: SETTINGS_VERSION_V3,
        darkMode: "dark",
      });
      expect(setItem).toHaveBeenCalledTimes(1);
      await runDataMigration();
      expect(setItem).toHaveBeenCalledTimes(1);
    } finally {
      setItem.mockRestore();
    }
  });

  test("reports a failed migration write to callers that require ready storage", async () => {
    globalThis.GM = {
      getValue: jest.fn(async () =>
        JSON.stringify({ version: SETTINGS_VERSION_V3, darkMode: true })
      ),
      setValue: jest.fn(async () => {
        throw new Error("migration write failed");
      }),
      deleteValue: jest.fn(),
    };
    const { runDataMigration: migrateGmData } = loadGmStorageModule();

    await expect(migrateGmData()).resolves.toBe(false);
  });

  test("getSettingWithDefault returns current settings for stored v1 data", async () => {
    const oldSetting = {
      uiLang: "zh",
      transApis: [
        {
          apiSlug: "openai",
          apiName: "OpenAI",
          systemPrompt: "custom batch prompt",
        },
      ],
    };
    window.localStorage.setItem(STOKEY_SETTING, JSON.stringify(oldSetting));

    const setting = await getSettingWithDefault();

    expect(setting.version).toBe(SETTINGS_VERSION_V3);
    expect(setting.translationRouterVersion).toBe(2);
    const migratedOpenAI = setting.transApis.find(
      (api) => api.apiSlug === "openai"
    );
    expect(migratedOpenAI.batchPromptSlug).toMatch(/^prompt_migrated_batch_/);
    expect(migratedOpenAI).not.toHaveProperty("systemPrompt");
  });

  test.each([
    [undefined, true, "dark"],
    [SETTINGS_VERSION_V2, false, "light"],
    [SETTINGS_VERSION_V3, true, "dark"],
    [SETTINGS_VERSION_V3, "auto", "auto"],
  ])(
    "normalizes version %p and theme %p without persisting a migration",
    async (version, darkMode, expected) => {
      const oldSetting = { version, darkMode, uiLang: "en" };
      const serialized = JSON.stringify(oldSetting);
      window.localStorage.setItem(STOKEY_SETTING, serialized);
      const setItem = jest.spyOn(window.Storage.prototype, "setItem");
      try {
        await expect(getSettingWithDefault()).resolves.toMatchObject({
          version: SETTINGS_VERSION_V3,
          darkMode: expected,
          uiLang: "en",
        });
        expect(setItem).not.toHaveBeenCalled();
        expect(window.localStorage.getItem(STOKEY_SETTING)).toBe(serialized);
        expect(oldSetting.darkMode).toBe(darkMode);
      } finally {
        setItem.mockRestore();
      }
    }
  );

  test("merges the language variant default without overriding an explicit choice", async () => {
    window.localStorage.setItem(
      STOKEY_SETTING,
      JSON.stringify({ version: SETTINGS_VERSION_V3, uiLang: "zh" })
    );
    await expect(getSettingWithDefault()).resolves.toMatchObject({
      translateVariants: true,
    });

    window.localStorage.setItem(
      STOKEY_SETTING,
      JSON.stringify({
        version: SETTINGS_VERSION_V3,
        translateVariants: false,
      })
    );
    await expect(getSettingWithDefault()).resolves.toMatchObject({
      translateVariants: false,
    });
  });

  test("keeps clipboard auto-translation opt-in for existing settings", async () => {
    window.localStorage.setItem(
      STOKEY_SETTING,
      JSON.stringify({ version: SETTINGS_VERSION_V3, uiLang: "zh" })
    );
    await expect(getSettingWithDefault()).resolves.toMatchObject({
      autoTranslateClipboard: false,
    });

    window.localStorage.setItem(
      STOKEY_SETTING,
      JSON.stringify({
        version: SETTINGS_VERSION_V3,
        autoTranslateClipboard: true,
      })
    );
    await expect(getSettingWithDefault()).resolves.toMatchObject({
      autoTranslateClipboard: true,
    });
  });

  test("does not replace explicitly stored Tencent entry points", async () => {
    window.localStorage.setItem(
      STOKEY_SETTING,
      JSON.stringify({
        version: SETTINGS_VERSION_V3,
        inputRule: { apiSlug: OPT_TRANS_TENCENT },
        tranboxSetting: { apiSlugs: [OPT_TRANS_TENCENT] },
        subtitleSetting: { apiSlug: OPT_TRANS_TENCENT },
      })
    );

    await expect(getSettingWithDefault()).resolves.toMatchObject({
      inputRule: { apiSlug: OPT_TRANS_TENCENT },
      tranboxSetting: { apiSlugs: [OPT_TRANS_TENCENT] },
      subtitleSetting: { apiSlug: OPT_TRANS_TENCENT },
    });
  });

  test("keeps an explicitly stored subtitle chunk length", async () => {
    // 新默认值只影响新配置；已有用户明确保存的 2000 不应被默认设置覆盖。
    expect(DEFAULT_SUBTITLE_SETTING.chunkLength).toBe(1000);
    window.localStorage.setItem(
      STOKEY_SETTING,
      JSON.stringify({
        version: SETTINGS_VERSION_V2,
        subtitleSetting: { chunkLength: 2000 },
      })
    );

    const setting = await getSettingWithDefault();

    expect(setting.subtitleSetting.chunkLength).toBe(2000);
  });

  test("normalizes legacy default thinking effort only in the loaded setting", async () => {
    const storedSetting = {
      version: SETTINGS_VERSION_V3,
      transApis: [
        {
          apiSlug: "openai",
          apiType: OPT_TRANS_OPENAI,
          model: "gpt-5.6-sol",
          thinkingMode: "enabled",
          thinkingEffort: "_default",
        },
      ],
    };
    window.localStorage.setItem(STOKEY_SETTING, JSON.stringify(storedSetting));

    const setting = await getSettingWithDefault();

    const openai = setting.transApis.find((api) => api.apiSlug === "openai");
    expect(openai.thinkingEffort).toBeNull();
    expect(readStoredJson(STOKEY_SETTING)).toEqual(storedSetting);
  });

  test("normalizes thinking settings for a fresh installation", async () => {
    const setting = await getSettingWithDefault();
    const deepseek = setting.transApis.find(
      (api) => api.apiType === OPT_TRANS_DEEPSEEK
    );

    expect(deepseek).toMatchObject({
      thinkingMode: "disabled",
      thinkingEffort: null,
    });
  });

  test("enables only local/native services for a fresh installation", async () => {
    const setting = await getSettingWithDefault();

    expect(setting.transApis).toHaveLength(DEFAULT_API_LIST.length);
    expect(
      setting.transApis
        .filter((api) => !api.isDisabled)
        .map((api) => api.apiType)
    ).toEqual([OPT_TRANS_CHARLIE_AUTO]);
  });

  test.each([1, SETTINGS_VERSION_V2, SETTINGS_VERSION_V3])(
    "preserves saved service activation choices from settings version %p",
    async (version) => {
      const savedApis = [
        {
          ...DEFAULT_API_LIST.find((api) => api.apiType === OPT_TRANS_OPENAI),
          isDisabled: false,
          sortOrder: -1,
          key: "saved-key",
        },
        {
          ...DEFAULT_API_LIST.find(
            (api) => api.apiType === OPT_TRANS_MICROSOFT
          ),
          isDisabled: true,
          sortOrder: 999,
        },
        {
          apiSlug: "legacy-tencent",
          apiType: OPT_TRANS_TENCENT,
        },
      ];
      const storedSetting = { version, transApis: savedApis };
      window.localStorage.setItem(
        STOKEY_SETTING,
        JSON.stringify(storedSetting)
      );

      const setting = await getSettingWithDefault();

      expect(setting.transApis).toHaveLength(savedApis.length + 1);
      expect(
        setting.transApis.some((api) => api.apiType === OPT_TRANS_CHARLIE_AUTO)
      ).toBe(true);
      savedApis.forEach((savedApi) => {
        const loadedApi = setting.transApis.find(
          (api) => api.apiSlug === savedApi.apiSlug
        );
        [
          "apiSlug",
          "apiName",
          "apiType",
          "isDisabled",
          "sortOrder",
          "key",
        ].forEach((field) => {
          if (Object.prototype.hasOwnProperty.call(savedApi, field)) {
            expect(loadedApi).toHaveProperty(field, savedApi[field]);
          } else {
            expect(loadedApi).not.toHaveProperty(field);
          }
        });
      });
      expect(readStoredJson(STOKEY_SETTING)).toEqual(storedSetting);
    }
  );

  test.each(["none", "minimal", "_default"])(
    "loads legacy Astra disabled effort %s as low without rewriting storage",
    async (thinkingEffort) => {
      const storedSetting = {
        version: SETTINGS_VERSION_V3,
        transApis: [
          {
            apiSlug: "openai",
            apiType: OPT_TRANS_OPENAI,
            model: "gpt-6-astra",
            thinkingMode: "disabled",
            thinkingEffort,
          },
        ],
      };
      window.localStorage.setItem(
        STOKEY_SETTING,
        JSON.stringify(storedSetting)
      );
      const setting = await getSettingWithDefault();
      const openai = setting.transApis.find((api) => api.apiSlug === "openai");
      expect(openai.thinkingEffort).toBe("low");
      expect(readStoredJson(STOKEY_SETTING)).toEqual(storedSetting);
    }
  );

  test("GM storage reports a clear error when GM APIs are unavailable", async () => {
    const { storage } = loadGmStorageModule();

    await expect(storage.get("missing-gm")).rejects.toThrow(
      "GM API is not available"
    );
  });

  test("GM storage uses KISS_GM when it is available", async () => {
    const stored = new Map();
    window.KISS_GM = {
      setValue: jest.fn(async (key, value) => stored.set(key, value)),
      getValue: jest.fn(async (key) => stored.get(key)),
      deleteValue: jest.fn(async (key) => stored.delete(key)),
    };
    globalThis.GM = {
      setValue: jest.fn(),
      getValue: jest.fn(),
      deleteValue: jest.fn(),
    };
    const { storage } = loadGmStorageModule();

    await storage.setObj("gm-key", { local: true });
    await expect(storage.getObj("gm-key")).resolves.toEqual({ local: true });
    await storage.del("gm-key");

    expect(window.KISS_GM.setValue).toHaveBeenCalledWith(
      "gm-key",
      JSON.stringify({ local: true })
    );
    expect(window.KISS_GM.getValue).toHaveBeenCalledWith("gm-key");
    expect(window.KISS_GM.deleteValue).toHaveBeenCalledWith("gm-key");
    expect(globalThis.GM.setValue).not.toHaveBeenCalled();
    expect(globalThis.GM.getValue).not.toHaveBeenCalled();
    expect(globalThis.GM.deleteValue).not.toHaveBeenCalled();
    expect(stored.has("gm-key")).toBe(false);
  });

  test("GM storage uses native GM storage APIs without KISS_GM", async () => {
    const stored = new Map();
    globalThis.GM = {
      setValue: jest.fn(async (key, value) => stored.set(key, value)),
      getValue: jest.fn(async (key) => stored.get(key)),
      deleteValue: jest.fn(async (key) => stored.delete(key)),
    };
    globalThis.GM_setValue = jest.fn();
    globalThis.GM_getValue = jest.fn();
    globalThis.GM_deleteValue = jest.fn();
    const { storage } = loadGmStorageModule();

    await storage.setObj("native-gm-key", { ios: true });
    await expect(storage.getObj("native-gm-key")).resolves.toEqual({
      ios: true,
    });
    await storage.del("native-gm-key");

    expect(globalThis.GM.setValue).toHaveBeenCalledWith(
      "native-gm-key",
      JSON.stringify({ ios: true })
    );
    expect(globalThis.GM.getValue).toHaveBeenCalledWith("native-gm-key");
    expect(globalThis.GM.deleteValue).toHaveBeenCalledWith("native-gm-key");
    expect(globalThis.GM_setValue).not.toHaveBeenCalled();
    expect(globalThis.GM_getValue).not.toHaveBeenCalled();
    expect(globalThis.GM_deleteValue).not.toHaveBeenCalled();
    expect(stored.has("native-gm-key")).toBe(false);
  });

  test("GM storage falls back to legacy GM storage APIs", async () => {
    const stored = new Map();
    globalThis.GM = {};
    globalThis.GM_setValue = jest.fn(async (key, value) =>
      stored.set(key, value)
    );
    globalThis.GM_getValue = jest.fn(async (key) => stored.get(key));
    globalThis.GM_deleteValue = jest.fn(async (key) => stored.delete(key));
    const { storage } = loadGmStorageModule();

    await storage.setObj("legacy-gm-key", { ios: true });
    await expect(storage.getObj("legacy-gm-key")).resolves.toEqual({
      ios: true,
    });
    await storage.del("legacy-gm-key");

    expect(globalThis.GM_setValue).toHaveBeenCalledWith(
      "legacy-gm-key",
      JSON.stringify({ ios: true })
    );
    expect(globalThis.GM_getValue).toHaveBeenCalledWith("legacy-gm-key");
    expect(globalThis.GM_deleteValue).toHaveBeenCalledWith("legacy-gm-key");
    expect(stored.has("legacy-gm-key")).toBe(false);
  });
});
