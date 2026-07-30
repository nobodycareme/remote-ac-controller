[简体中文](../中文/参与贡献.md) | **English**

# Contributing

Thanks for your interest in improving the Remote AC Controller project!

## Getting Started

This is a Monorepo with two main subsystems:

- `firmware/` — ESP8266 firmware (PlatformIO / Arduino).
- `cloud/` — backend (Node.js / Fastify / TypeScript) and frontend
  (Vue 3 / TypeScript), plus `broker/`, `deploy/`, and `tools/`.

See the root [`README.md`](./README.md) and the [`docs/`](..) directory
for architecture and setup details.

## Development Workflow

1. Fork and clone the repository.
2. For firmware changes, use the existing `firmware/tools/dev.ps1` entry
   point — do **not** invoke `pio`/`platformio`/`esptool` directly.
3. For cloud changes, install dependencies in `cloud/backend` and
   `cloud/frontend`, then run the test suites.
4. Run the root-level helper scripts before opening a pull request:
   - `tools/test-all.ps1` — runs firmware and cloud test suites.
   - `tools/build-all.ps1` — runs the firmware and cloud builds.
5. Open a pull request against `main`.

## Code Style

- Keep commits focused and use clear, conventional commit messages.
- Add or update tests for behavior changes.
- Ensure `firmware-ci` and `cloud-ci` (GitHub Actions) pass.

## Security

- **Never** commit secrets: passwords, private keys, tokens, cookies,
  sessions, real IR data, or production environment files.
- Use `.example` files for configuration templates.
- Report security issues per [`SECURITY.md`](./security.md).

## License

By contributing, you agree that your contributions will be licensed under
the [Apache License 2.0](../../LICENSE).
