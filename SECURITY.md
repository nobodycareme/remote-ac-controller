# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| v1.0.0  | ✅ |

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
