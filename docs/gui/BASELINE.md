# GUI development environment

Use Python 3.12 or 3.13 with the repository's `uv.lock` and the frontend's `package-lock.json`. Current package versions and commands are specified in [installation](../INSTALLATION.md) and [contributing](../../CONTRIBUTING.md); lockfiles are authoritative.

The GUI is an optional client of the same application services used by headless studies. FastAPI exposes validated requests and recorded evidence; React and TypeScript render the controls, inspectors and replay. Browser checks exercise actual services and isolated temporary workspaces.

Start development in a branch with a clean working tree. Use a separate environment and workspace for tests, preserve running studies, and record the source revision with verification results. See [architecture](../ARCHITECTURE.md), [contracts](CONTRACTS.md) and [integration checks](INTEGRATION_POLICY.md).
