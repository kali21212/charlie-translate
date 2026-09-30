# Upstream and provenance

Charlie Translate is an enhanced derivative of **KISS Translator**.

- Upstream: https://github.com/fishjar/kiss-translator
- Upstream default development branch at project start: `dev`
- License: GNU GPL v3
- Local upstream remote: `upstream`
- Our public repository: https://github.com/kali21212/charlie-translate
- Our default branch: `main`

## Reuse policy

We preserve upstream attribution and GPL-3.0 obligations. Charlie-specific changes are tracked in CHANGELOG.md and Git history. No upstream history is rewritten. Updates should flow:

`upstream -> integration branch -> tests/audit -> PR -> main -> release`

Additional projects are used only where their licenses and security posture are compatible. MTranServer is integrated by protocol/API and remains a separate Apache-2.0 project.
