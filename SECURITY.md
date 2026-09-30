# Security Policy

## Design goals

Charlie Translate is intended to be privacy-first and least-privilege.

- Fresh installs default to loopback MTranServer. Browser-native translation is available. Cloud providers, online dictionaries/suggestions, remote rules and update checks require opt-in; saved settings are preserved.
- Never embed private API keys or production credentials in source control.
- Do not silently translate editable secrets.
- On account/security/authentication routes, input translation and clipboard auto-translation are disabled by default.
- Explicit selection translation remains available so users can translate non-secret labels and documentation.
- Cloud/AI providers are opt-in and their data-handling terms remain the user's/provider's responsibility.

## Enforced boundaries and limitations

Input translation rechecks current routes (including encoded paths/hash/query), password/OTP/named-secret fields and open shadow roots before dispatch, so SPA navigation, late fields and a manual input toggle cannot bypass the guard. Closed shadow roots and unlabelled secrets cannot be fully detected.

The popup reads clipboard text only with optional permission and after active-tab/all-frame inspection. Sensitive routes, secret fields, unavailable inspection and navigation changes block reads. Clipboard data has no reliable origin: text copied earlier from another page may still contain secrets. Automatic clipboard translation defaults off.

Explicit selection, hover, subtitle and page-text translation remain available and send text to the selected provider; they are not semantic secret filters. MTranServer accepts HTTP(S) loopback URLs without embedded credentials, omits empty bearer tokens and never automatically falls back to cloud. Bind the independent service to loopback; its initial model downloads/update behavior are governed by that service.

For the Chrome client, final request URLs are revalidated after request hooks and redirects are rejected before text can be resent to another host. Web/userscript clients are outside this V1 verification scope.

Upstream `<all_urls>`, scripting, storage and other feature permissions remain. No telemetry or remote installer was added. Optional sync can upload settings including provider credentials; use only a trusted destination.

## Dependency security

See [DEPENDENCY_AUDIT.md](docs/DEPENDENCY_AUDIT.md) for baseline, runtime/build classification and residual findings. `audit:dependencies` checks full and production trees with exact advisory/version/severity/path exceptions. New exposure, audit errors and expired exceptions fail CI; review by 2026-11-30. Remaining findings are not described as fixed.

Production audit must have zero vulnerabilities, with no runtime exceptions. React Router was migrated to 7.18.4 to repair both previously retained medium runtime advisories. The remaining exceptions cover development/build dependencies only.

Development start scripts bind to `127.0.0.1`. Legacy CRA server and build SVG vulnerabilities need a tested tooling migration; do not expose the dev server publicly or build untrusted SVGs.

## Reporting vulnerabilities

Please open a GitHub Security Advisory for vulnerabilities when possible. Do not post live credentials, tokens, personal data, or exploit secrets in public issues.

## Dependency and upstream review

Before adopting new code:
1. verify license;
2. inspect maintenance activity;
3. review network, shell, credential, and permission behavior;
4. run tests and dependency/security checks;
5. record provenance and changes.
