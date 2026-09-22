# GUI integration checks

Develop changes in an isolated branch and test workspace. Keep application semantics independent of presentation: a UI change must not silently alter scenario order, solver settings, protocol versions or analysis denominators.

## Evidence for a change

A pull request should identify the concrete behavior, source revision, affected contracts and relevant test results. Include screenshots when visual behavior changes and disclose unavailable checks. Record automated accessibility results separately from platform-specific assistive-technology review.

Run Python tests, Ruff, mypy, frontend formatting/lint/build, generated-contract drift checks, real browser workflows and installed-wheel smoke checks as described in [distribution qualification](../RELEASE-CHECKS.md). Later edits invalidate evidence for the changed files and require the relevant checks again.

## Recovery

Preserve working-tree changes, immutable run evidence and original scenario data. Reproduce a failure in an isolated workspace, then prepare a focused corrective or revert commit. Stop only processes owned by the test. Do not resume a scientific study with changed method inputs under its previous identity.
