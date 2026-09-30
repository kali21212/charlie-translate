# Security Policy

## Design goals

Charlie Translate is intended to be privacy-first and least-privilege.

- Prefer browser-native or local translation when practical.
- Never embed private API keys or production credentials in source control.
- Do not silently translate editable secrets.
- On account/security/authentication routes, input translation and clipboard auto-translation are disabled by default.
- Explicit selection translation remains available so users can translate non-secret labels and documentation.
- Cloud/AI providers are opt-in and their data-handling terms remain the user's/provider's responsibility.

## Reporting

Please open a GitHub Security Advisory for vulnerabilities when possible. Do not post live credentials, tokens, personal data, or exploit secrets in public issues.

## Dependency and upstream review

Before adopting new code:
1. verify license;
2. inspect maintenance activity;
3. review network, shell, credential, and permission behavior;
4. run tests and dependency/security checks;
5. record provenance and changes.
