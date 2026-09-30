import { applySensitivePageGuards, isSensitivePage } from "./securityGuard";

describe("Charlie sensitive-page guard", () => {
  test.each([
    "https://github.com/settings/security",
    "https://example.com/login",
    "https://example.com/auth/mfa",
    "https://example.com/account/passkey",
    "https://example.com/#/login",
    "https://example.com/settings/tokens",
    "https://example.com/%73ecurity",
    "https://example.com?route=auth",
    "https://example.com/login?bad=%ZZ",
    "https://example.com/%73ecurity?bad=%ZZ",
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

  test("detects late OTP and secret fields inside open shadow roots", () => {
    const doc = document.implementation.createHTMLDocument();
    expect(isSensitivePage("https://example.com/docs", doc)).toBe(false);
    const host = doc.createElement("div");
    doc.body.appendChild(host);
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = '<input autocomplete="one-time-code">';
    expect(isSensitivePage("https://example.com/docs", doc)).toBe(true);
  });

  test("does not modify ordinary-page settings", () => {
    const setting = {
      inputRule: { transOpen: true },
      autoTranslateClipboard: true,
    };
    expect(
      applySensitivePageGuards({
        href: "https://example.com/docs",
        setting,
        doc: { querySelector: () => null },
      })
    ).toBe(false);
    expect(setting.inputRule.transOpen).toBe(true);
  });
});
