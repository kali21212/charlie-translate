# Security Audit Baseline

Date: 2026-09-30

## Gate result

**PRE-RELEASE / NOT STORE-READY**

The inherited KISS Translator dependency tree currently reports 122 advisories under the package-manager production audit view: 73 high, 52 moderate, and 11 low. No critical advisory was reported.

The findings are dominated by the inherited Create React App / react-scripts build chain and transitive tooling, with additional findings in libraries such as webdav. Because browser extensions handle page content and may hold API credentials, Charlie Translate treats this as release-gating technical debt rather than ignoring the audit.

## What passed

- Charlie sensitive-page guard regression tests.
- MTranServer request/response compatibility tests.
- Existing API configuration regression tests.
- Chrome production build.
- Git whitespace/diff check.

## Required before store release

- Triage advisories into build-time-only versus bundled/runtime exposure.
- Upgrade or replace vulnerable runtime dependencies first.
- Reduce reliance on the legacy CRA toolchain; evaluate WXT/Vite migration.
- Add automated dependency and static-analysis gates.
- Re-run browser permission/network/credential-flow review.
- Produce a packaged-extension artifact audit before publishing.

The public repository may be used for transparent development while this gate remains open. A GitHub/Chrome Store production release should not be declared security-cleared until the gate is closed.
