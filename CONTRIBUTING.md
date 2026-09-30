# Contributing

Contributions are welcome.

Please keep changes focused, testable, and auditable. For code changes:

1. branch from `main`;
2. add behavior-focused regression tests where they improve fault detection;
3. use Node.js 22 and `corepack pnpm@10.15.1 install --frozen-lockfile`, then run `test:charlie`, `test:dependency-compatibility`, `audit:dependencies`, `build:chrome` and `git diff --check`;
4. document user-visible changes in `CHANGELOG.md`;
5. open a pull request.

Because this project derives from KISS Translator, contributions are distributed under GPL-3.0. Do not submit code copied from projects with incompatible or unclear licensing.

For security-sensitive changes, describe data flows, permissions, network endpoints, and failure modes in the pull request.

Do not run audit auto-fixes or force major overrides without compatibility validation. Exceptions require exact advisory, version, path, rationale, exposure evidence and review date in `docs/dependency-audit-exceptions.json`. Keep the pinned pnpm tool and frozen lockfile consistent.

CI checks the actual PR head. Merge only after that commit passes tests, dependency compatibility, reviewed audit and Chrome build. A pass from an earlier commit does not satisfy this gate. Keep credentials out of commits and PR descriptions.
