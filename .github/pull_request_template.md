# Pull Request

## Summary

<!-- What does this change do, and why? One or two sentences. -->

## Affected area

- [ ] `firmware/` (ESP8266)
- [ ] `cloud/backend/`
- [ ] `cloud/frontend/`
- [ ] `cloud/broker/` (Mosquitto config)
- [ ] `docs/` / `hardware/`
- [ ] Repository tooling / CI

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Build / CI

## Verification

Describe what you actually ran. Do not tick a box you did not execute.

- [ ] `pwsh tools/test-all.ps1` passed
- [ ] `pwsh tools/build-all.ps1` passed
- [ ] Verified on real hardware (state the board and how)
- [ ] Not applicable (documentation-only change)

<!-- Paste the relevant tail of the output if it helps review. -->

## Security checklist

These are hard requirements. A PR that fails any of them will not be merged.

- [ ] No credentials, tokens, passwords, private keys or certificates are added
- [ ] No `secrets.h`, `cloud_secrets.h`, `.env`, `*.db`, `*.pem`, `*.key` is committed
- [ ] No production hostname, IP address or account is hard-coded
- [ ] Real-IR transmission remains disabled by default
- [ ] No file from `Private/`, `Evidence/` or any internal archive is included

## Breaking changes

<!-- State "None", or describe the migration path. -->

## Related issues

<!-- e.g. Closes #12 -->
