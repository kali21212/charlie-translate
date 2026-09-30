# Dependency audit — Charlie V1 (2026-09-30)

| Scope | Before | After | Interpretation |
| --- | --- | --- | --- |
| Full lockfile | 136: 73 high, 52 moderate, 11 low | 13: 3 high, 10 moderate | Includes build/test/dev server |
| Production tree after correct classification | Not comparable until react-scripts moved to dev | 2 moderate, no high/critical | Both React Router v6 applicability findings below |

The original 136 count covers 122 advisory records across 43 packages; version/path multiplicity explains the difference. [dependency-audit-baseline.json](dependency-audit-baseline.json) preserves package/path evidence at `1f720ae7af3b779396f5219a1aa721eb8b5661cc`; it is not a CI allowlist.

The manifest incorrectly treated react-scripts as production, pulling CRA/Webpack/Jest/dev servers into `audit --prod`. It is now a devDependency. Real runtime risks were separately patched: DOMPurify, WebDAV XML/glob parsing, query-string URI decoding, selector parsing and routing. Emotion Babel/macro ancestry and remark's uvu are tooling paths even when a package-manager production tree includes them; classification alone is not a fix.

## Repairs

Direct/range updates include DOMPurify 3.4.16, WebDAV 5.11.0, React Router DOM 6.30.6, postcss-selector-parser 6.1.3, Babel 7.29.7 and bestzip 2.2.7. Removed fast-xml-parser 4.5.4 override: it forced updated WebDAV onto a vulnerable/incompatible major; the updated client uses its native 5.x parser dependency.

Version-scoped overrides patch minimatch 3/5, brace-expansion 1/2, AJV 6/8, PostCSS 8, picomatch 2/4, YAML 1, js-yaml 3/4, Rollup 2, nanoid 3 and fast-uri 3. Patched jsonpath, qs, node-forge, lodash, shell-quote, decode-uri-component, underscore and @tootallnate/once. serialize-javascript 7.0.5 is a deliberate major override: Node 22 satisfies its engine, and Chrome minification build verifies usage.

pnpm 10.15.1 is pinned via packageManager/Corepack. pnpm 11 ignored the original package.json overrides during inspection; do not silently substitute tools. No forced SVGO/UUID/React Router/dev-server major change was used to obtain a cosmetic zero audit count.

## Residual findings (not fixed)

| Package | Remaining | Exposure and decision |
| --- | --- | --- |
| react-router 6.30.6 | 2 moderate, runtime | GHSA-wrjc-x8rr-h8h6 concerns untrusted navigation; options use declarative HashRouter/static local NavLink paths. GHSA-337j-9hxr-rhxg concerns manual SSR/data hydration and excludes declarative mode. No SSR/framework/data router is used. Reassess if dynamic external navigation or hydration is introduced. |
| webpack-dev-server 4.15.2 | 6 moderate, dev-only | CRA start environment, absent from extension. Start scripts bind loopback. Fixed 5.x needs a compatible toolchain migration. Local binding does not completely fix attacks triggered by malicious browsing. |
| webpack-dev-middleware 5.3.4 | 1 high, dev-only | CRA dev server, absent from Chrome artifact. Fixed 7.x has compatibility changes. Do not expose dev server or process untrusted dev assets. |
| svgo 1.3.2 | 2 high, 1 moderate, build-only | SVGR 5 needs v1 configuration; v2 override breaks it. Input is static repository SVG; no arbitrary user SVG sanitization boundary or runtime removeScripts filter. Requires tested SVGR migration. |
| uuid 8.3.2 | 1 moderate, dev-only | SockJS transport uses require('uuid').v4; advisory concerns v3/v5/v6 buffer handling. UUID 11 has API/engine changes and is not forced. |

The Chrome artifact excludes development servers, but developers can still be exposed while running/building. These exceptions do not approve publicly exposing a development server.

## Verification and CI

Real dependency tests exercise WebDAV PROPFIND XML against an ephemeral loopback fixture, malformed URI decoding and selector parsing. Behavior tests cover providers/defaults/storage, input, clipboard, popup, sync and declarative routing. Chrome build validates actual extension packaging/minification. Real translation quality requires a separately installed MTranServer/model and browser acceptance.

`audit:dependencies` checks full and prod trees. [dependency-audit-exceptions.json](dependency-audit-exceptions.json) lists exact IDs/packages/severities/versions/paths, rationale and review deadline. Any new finding, changed version/path/severity, dev-only finding appearing in prod, service error or expired review fails. Raw audits are saved under ignored `tmp/`.

PR CI checks `github.event.pull_request.head.sha`: frozen install, tests, real dependency compatibility, reviewed audit, Chrome build and commit whitespace checks. Earlier commit checks cannot satisfy a newer head.
