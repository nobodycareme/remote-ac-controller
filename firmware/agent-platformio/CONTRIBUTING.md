# Contributing to Remote AC Controller

Thank you for your interest in contributing! This project is a mobile remote AC control system with ESP8266 firmware and a Node.js cloud backend.

## How to Contribute

1. **Fork** the repository ([firmware](https://github.com/nobodycareme/remote-ac-controller) / [cloud](https://github.com/nobodycareme/remote-ac-controller))
2. **Create a branch** (git checkout -b feature/your-feature)
3. **Make your changes** and ensure tests pass
4. **Commit** with a descriptive message (git commit -m "Add: describe your change")
5. **Push** and open a Pull Request

## Development Setup

### Firmware
- PlatformIO with ESP8266 toolchain (see README.md)
- Build via .\tools\dev.ps1 clean-build -Profile public

### Cloud Backend
- Node.js >= 24
- cd backend && npm install && npm test

### Cloud Frontend
- cd frontend && npm install && npm run build

## Code Guidelines
- Follow existing code style conventions
- Add tests for new features
- The public profile must never contain secrets or real IR codes
- Do not commit secrets.h, cloud_secrets.h, or real credentials

## License
By contributing, you agree that your contributions will be licensed under the Apache License 2.0.