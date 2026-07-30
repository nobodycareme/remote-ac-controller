# Security Policy

## Reporting a Vulnerability

**Do NOT open a public issue** for security vulnerabilities.

Please report security issues privately to the project maintainer.

### What to Include
- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Possible mitigations (if known)

### Scope

This project controls physical hardware (air conditioner). Please pay special attention to:

- **MQTT/TLS**: certificate validation, man-in-the-middle risks
- **Authentication**: session handling, CSRF, credential storage
- **IR command injection**: ability to transmit arbitrary IR codes
- **Firmware OTA**: integrity and authenticity of updates

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Security Design

Public builds contain **zero credentials** and **read-only IR** capability.
Private builds require secrets.h which is never committed to version control.
See RECOVERY_PROVENANCE.md for the full security provenance.