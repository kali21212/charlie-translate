/**
 * Charlie security guardrails for credential-sensitive pages.
 * Ordinary page text and explicit selection translation remain available.
 */
const SENSITIVE_PATH_RE =
  /(?:^|\/)(?:login|log-in|signin|sign-in|auth|oauth|credential|passkey|security|2fa|mfa|billing|checkout|wallet|banking)(?:\/|$)/i;

export function isSensitivePage(href = "", doc = globalThis.document) {
  try {
    const url = new URL(href);
    if (SENSITIVE_PATH_RE.test(url.pathname)) return true;
  } catch (_err) {
    // Invalid or opaque URLs fall through to DOM checks.
  }

  try {
    return Boolean(doc?.querySelector?.('input[type="password"]'));
  } catch (_err) {
    return false;
  }
}

export function applySensitivePageGuards({ href = "", setting, doc } = {}) {
  if (!setting || !isSensitivePage(href, doc)) return false;

  // Never transform editable secrets or silently translate clipboard content
  // on account/security surfaces. Explicit selection translation stays usable.
  if (setting.inputRule) setting.inputRule.transOpen = false;
  setting.autoTranslateClipboard = false;
  return true;
}
