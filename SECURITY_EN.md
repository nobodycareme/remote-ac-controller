[简体中文](./SECURITY.md) | **English**

# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main branch (pre-v1.0.0) | ✅ |

## Scope of this Public Repository

This repository is the **open-source release** of the Remote AC Controller system.
It intentionally contains **no production secrets**:

- No production Wi-Fi credentials.
- No production MQTT account names or passwords.
- No TLS private keys (`ca.key`, `server.key`) or live server certificates.
- No real infrared (IR) capture data or canonical IR payloads.
- No databases, production environment files, or deployment secrets.
- No private keys, tokens, cookies, or sessions.

All such material lives only in the maintainer's private, non-public
infrastructure and is **never** published here.

## Safe Defaults for Cloners

After cloning, the firmware and cloud components default to **safe,
non-production** behavior:

- The firmware public profile does not embed production Wi-Fi, MQTT
  accounts, or production domain configuration, and does not enable real
  IR transmission.
- The cloud default configuration binds to `localhost`, uses `example.com`
  placeholders, an empty/test database, a local test MQTT address, IR
  disabled, automation disabled, and requires the operator to supply their
  own cookie/session signing key.

## Reporting a Vulnerability

If you discover a security vulnerability in the **code published in this
repository**, please report it privately rather than opening a public issue.

- Use GitHub's **Private vulnerability reporting** for this repository if
  enabled.
- Otherwise, contact the maintainer privately and allow reasonable time for
  a fix before any public disclosure.

Please include:
- A description of the vulnerability and its impact.
- Steps to reproduce (or a proof-of-concept).
- Affected version(s) and environment.

You will receive an acknowledgement and, once triaged, information about
remediation and coordinated disclosure.

## Responsible Use

This project controls a physical air conditioner via infrared signals.
Operators are responsible for complying with local regulations, respecting
the devices they control, and securing any self-hosted deployment (MQTT
credentials, TLS, network exposure).

## Dependency Vulnerability Status

Last reviewed: 2026-07-30 (pre-v1.0.0, main branch).

`npm audit` reports the following. **No `npm audit fix --force` was applied**
— every available fix is a **major-version breaking change** (e.g.
`fastify@5.11.0`, `@fastify/static@10.1.2`, `vitest@4.1.10`, `vite@8`), and
force-upgrading would break the build and runtime contracts. Remediation is
tracked as a planned follow-up and is a **prerequisite for the v1.0.0
release**.

| Package | Severity | Type | In production runtime? | Notes |
|---------|----------|------|-----------------------|-------|
| `vitest` (backend, direct) | critical | dev/test | No | Only affects the Vitest UI server locally; never shipped. |
| `esbuild` (frontend, transitive) | critical | dev | No | Dev-server only; not part of the production bundle. |
| `fastify` (backend, direct) | high | prod | Yes | DoS / `X-Forwarded-*` spoofing. Fix = `fastify@5.11.0` (major). |
| `@fastify/static` (backend, direct) | high | prod | Yes | Auth bypass via path traversal. Fix = `@fastify/static@10.1.2` (major). |
| `find-my-way`, `fast-uri`, `fast-json-stringify`, `glob`, `minimatch`, `brace-expansion`, `@fastify/*-compiler` (backend) | high | transitive | Via fastify | All resolved by the fastify major bump above. |
| `uuid` (backend) | moderate | prod | Yes | Bounds check; low exploitability in current usage. |
| remaining moderate (frontend/backend) | moderate | mixed | partial | See `npm audit` for detail. |

**Impact on release gates:**

- The two **critical** findings are confined to **development/test tooling**
  and are **not present in any deployed artifact**, so they do not block
  publishing the `main` branch.
- The **production-rated high** findings (`fastify`, `@fastify/static`) are
  real and must be remediated (major bumps + regression tests) **before** the
  `v1.0.0` release is cut. The `v1.0.0` tag/Release remains **withheld** until
  then (independent of the production server rotation gate).
- Maintainers should subscribe to the linked advisories and re-run `npm audit`
  after each dependency change.
