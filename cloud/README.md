# Remote AC Cloud

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Node.js](https://img.shields.io/badge/Node.js-%3E%3D24-green.svg)](https://nodejs.org/)

Cloud backend and frontend for mobile remote AC control. Provides REST + WebSocket API, MQTT device bridge, weather proxy, and Vue 3 web dashboard.

> **Sister repo** — firmware: [remote-ac-firmware](https://github.com/nobodycareme/remote-ac-controller)

---

## Architecture

`
┌──────────────┐     MQTT/TLS      ┌────────────────┐
│  ESP8266 FW  │ ◄───────────────► │  Cloud Backend  │
│  (NodeMCU)   │                   │  (Node.js 24+)  │
└──────────────┘                   ├────────────────┤
                                   │ Fastify + REST  │
                                   │ WebSocket       │
                                   │ MQTT (mosquitto)│
                                   │ SQLite          │
                                   │ Weather proxy   │
                                   └───────┬─────────┘
                                           │
                                   ┌───────┴─────────┐
                                   │  Cloud Frontend  │
                                   │  (Vue 3 + Vite)  │
                                   └─────────────────┘
`

## Quick Start

`ash
# Backend
cd backend
cp .env.example .env
npm install
npm run build
npm start

# Frontend (dev)
cd frontend
npm install
npm run dev

# Frontend (production build)
npm run build
`

## Project Structure

`
remote-ac-cloud/
├── backend/          # Node.js backend (Fastify + MQTT + SQLite)
│   ├── src/          # TypeScript source
│   ├── tests/        # Vitest test suite (78 tests)
│   ├── deploy/       # Systemd unit, deployment scripts
│   └── tools/        # CLI utilities (cert-monitor, etc.)
├── frontend/         # Vue 3 + Vite SPA
│   ├── src/          # Vue components, stores, API client
│   └── public/       # Static assets
├── broker/           # Mosquitto MQTT broker config
├── infra/            # Docker / docker-compose
├── packages/shared/  # Shared TypeScript types
├── tools/            # Dev/ops scripts
└── docs/             # Architecture docs
`

## Features

- **REST API**: device control, telemetry, scheduling, weather
- **WebSocket**: real-time device status push
- **MQTT Bridge**: bidirectional device communication over TLS
- **SQLite Store**: command history, telemetry, sessions
- **Authentication**: bcrypt/scrypt password hashing, session management, CSRF protection
- **IR Debug**: controlled IR debugging endpoints (read-only by default)
- **Automation**: schedule + temperature-hysteresis rule engine
- **Weather Proxy**: Open-Meteo with caching, decoupled from device state

## Testing

`ash
cd backend
npm test    # 78 tests across 10 suites
`

## Security

- TLS-encrypted MQTT (mosquitto with proper certificates)
- CSRF protection on all state-changing endpoints
- bcrypt/scrypt password hashing with auto-migration
- Rate limiting via @fastify/rate-limit
- No credentials in version control — see .env.example

## License

Apache License 2.0 — see [LICENSE](LICENSE).

Copyright 2026 张名扬 (Mingyang Zhang)