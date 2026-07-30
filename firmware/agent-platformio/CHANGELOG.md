# Changelog

## v0.4.0-cloud-foundation (2026-07-18)
### Security hardening
- **AUTH GATE**: Compile-time gate on `ENABLE_CONTROLLED_LIVE_AUTH` — public builds exclude secrets.h entirely; CAMPUS_USERNAME/PASSWORD undefined
- **AUTH GATE**: Business-layer final gate in `campus_auth_vendor.cpp` login()/logout() — even if CLI misses check, deepest layer refuses
- **AUTH GATE**: CLI gate on `campus login`/`campus logout`/`campus login-confirm-once`
- **IR GATE**: CLI + service-layer dual gate on `ir learn`/`ir send`/`ir cancel`
- **IR ADDRESS**: Separated `IR_MODULE_ADDRESS=0x00` (confirmed module) from `IR_BROADCAST_ADDRESS=0xFF` (discovery only)
- Three-layer defence: compile-time `#if`, CLI dispatch, business-layer final check
### Engineering cleanup
- Root firmware artifacts removed (8 files → archive)
- Historical logs moved to archive
- `review_work/`, `__pycache__/` removed
- Clean `.gitignore` — secrets, binaries, logs, IDE files
- `logs/README.md` explaining runtime-only log policy
### Workflow
- `dev.ps1` rewritten: Profile support (public/private), dynamic build_dir, clean-build verification
- `platformio.ini`: dynamic `build_dir = ${sysenv.PLATFORMIO_BUILD_DIR}`, profile-based build_flags
- Build output fixed to `C:\PioStable\build\Remote_AC_Controller\<profile>\`
- Upload with explicit COM port (dynamic detection, multi-device rejection)
### Documentation
- Version unified: `v0.4.0-cloud-foundation` (VERSION file, app_config.h, README, AGENTS)
- README, AGENTS.md, CHANGELOG updated
- Old six-env, old Core, old incomplete-auth sections removed

## v0.3.6 (2026-07-18)
- LIVE_CAMPUS_AUTH_PASS: Real Xidian campus network authentication successful
- INTERNET_VERIFICATION_PASS: Three external targets verified
- POST_LOGIN_60MIN_STABILITY_PASS: 94.6min stability test passed
- PERMANENT_BUILD_WORKFLOW_PASS: Stable <PIO_STABLE_ROOT> environment, genie-trash-free
- Xidian Srun non-standard success response handler (error=login_error whitelist)
- Root cause: genie-trash/win32-x64.exe holding PlatformIO lock files
- Single env consolidation: [env:nodemcuv2] only
- Runtime diagnostics: 14 serial commands in production firmware
- PUBLIC_NO_SECRET_BUILD_PASS: ENABLE_CONTROLLED_LIVE_AUTH=0
- Secure ZIP: forward-slash paths, CRC verified, sensitive scan pass

## v0.3.5 (2026-07-18)
- Single environment runtime diagnostics
- Two-env attempt (abandoned: PlatformIO instability)
- Direct CampusAuthVendor login path

## v0.3.4 (2026-07-17) — historical
- Six-env architecture (deprecated)
- No real auth (AUTH_BLOCKED, no secrets.h)
