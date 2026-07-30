[简体中文](./SUPPORT.md) | **English**

# Support

## Documentation

- Root [`README.md`](./README_EN.md) — system overview and quick start.
- [`docs/`](./docs) — architecture, hardware, wiring, IR learning, MQTT
  protocol, security model, scheduling, temperature automation, deployment,
  and troubleshooting.

## Self-Hosted Deployments

This repository provides source code only. Operators are responsible for
their own deployment, including:

- Securing the MQTT broker (credentials, ACLs, TLS).
- Generating and managing their own TLS certificates.
- Protecting the cloud backend (network exposure, secrets, database).
- Supplying their own IR codes for their specific air conditioner model.

## Getting Help

- Open a [GitHub Issue](https://github.com/nobodycareme/remote-ac-controller/issues)
  for bugs and feature requests.
- For security issues, follow [`SECURITY.md`](./SECURITY_EN.md) — do **not**
  open public issues for vulnerabilities.

## Scope

This is a community/open-source project. Support is provided on a best-effort
basis. The maintainer is not responsible for any damage, malfunction, or
unintended operation of air-conditioning equipment controlled via this system.
