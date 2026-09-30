import {
  applySensitivePageGuards,
  isSensitivePage,
} from "./securityGuard";

describe("Charlie sensitive-page guard", () => {
  test.each([
    "https://github.com/settings/security",
    "https://example.com/login",
    "https://example.com/auth/mfa",
    "https://example.com/account/passkey",
  ])("detects sensitive route %s", (href) => {
    expect(isSensitivePage(href, { querySelector: () => null })).toBe(true);
  });

  test("detects secret-entry fields even on neutral routes", () => {
    const doc = { querySelector: () => ({ type: "password" }) };
    expect(isSensitivePage("https://example.com/profile", doc)).toBe(true);
  });

  test("keeps selection translation while disabling secret-prone automation", () => {
    const setting = {
      autoTranslateClipboard: true,
      inputRule: { transOpen: true },
      tranboxSetting: { transOpen: true },
    };
    expect(
      applySensitivePageGuards({
        href: "https://github.com/settings/security",
        setting,
        doc: { querySelector: () => null },
      })
    ).toBe(true);
    expect(setting.inputRule.transOpen).toBe(false);
    expect(setting.autoTranslateClipboard).toBe(false);
    expect(setting.tranboxSetting.transOpen).toBe(true);
  });
});
