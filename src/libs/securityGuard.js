/**
 * Charlie security guardrails for credential-sensitive pages.
 * Ordinary page text and explicit selection translation remain available.
 */
const SENSITIVE_PATH_RE =
  /(?:^|[/#?=&._-])(?:login|log-in|signin|sign-in|auth|oauth|credentials?|passkeys?|password|security|tokens?|api-keys?|2fa|mfa|billing|checkout|wallet|banking)(?:[/#?=&._-]|$)/i;

// This function is also serialized by scripting.executeScript; keep it self-contained.
export function hasSensitiveFields(root = globalThis.document) {
  const selector =
    'input[type="password"], [autocomplete="current-password"], [autocomplete="new-password"], [autocomplete="one-time-code"], input[name*="token" i], input[name*="secret" i], input[name*="api_key" i], input[name*="apikey" i], textarea[name*="secret" i], textarea[name*="token" i]';
  const inspect = (scope) => {
    if (scope?.querySelector?.(selector)) return true;
    for (const element of scope?.querySelectorAll?.("*") || []) {
      if (element.shadowRoot && inspect(element.shadowRoot)) return true;
    }
    return false;
  };
  try {
    return inspect(root);
  } catch (_err) {
    return true;
  }
}

export function isSensitivePage(href = "", doc = globalThis.document) {
  try {
    const url = new URL(href);
    if (
      [url.pathname, url.hash, url.search].some((part) => {
        if (SENSITIVE_PATH_RE.test(part)) return true;
        try {
          return SENSITIVE_PATH_RE.test(decodeURIComponent(part));
        } catch (_err) {
          return false;
        }
      })
    )
      return true;
  } catch (_err) {
    // Invalid or opaque URLs fall through to DOM checks.
  }

  try {
    return hasSensitiveFields(doc);
  } catch (_err) {
    return true;
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
