#pragma once
/*
 * Campus portal TLS certificate pin (public information only — no secrets).
 *
 * Host:        portal.campus.example.edu  (Xidian University campus network portal)
 * Extracted:   2026-07-17 via system-trusted TLS from a PC on the open internet
 *              (CONNECT tunnel through the local HTTP proxy; the leaf cert is
 *               issued by a public CA and is NOT a proxy re-signed certificate).
 * Leaf cert:   CN=*.campus.example.edu, O=西安电子科技大学, C=CN, ST=陕西省, L=西安市
 * Issuer:      GlobalSign RSA OV SSL CA 2018  (public CA, NOT a MITM proxy CA)
 * Verify:      "Verify return code: 0 (ok)" — system trust chain validated.
 *
 * The ESP8266 uses BearSSL setFingerprint(CAMPUS_CERT_SHA1). If the server
 * ever presents a different leaf certificate, the handshake fails and campus
 * login is aborted with TLS_PIN_MISMATCH (credentials are NEVER sent).
 *
 * ROTATION: when NotAfter (2026-11-17) approaches, re-extract the certificate
 * (docs/03_协议与接口/TLS证书固定与更新.md) and update CAMPUS_CERT_SHA1 below.
 * Do NOT auto-trust a changed certificate.
 */
#define CAMPUS_CERT_SHA1        "F4:BD:59:32:8E:77:8C:CB:AD:6E:AE:85:86:59:36:FD:0D:28:47:F9"
#define CAMPUS_CERT_NOT_BEFORE  "2025-10-16"
#define CAMPUS_CERT_NOT_AFTER   "2026-11-17"
#define CAMPUS_CERT_ISSUER      "GlobalSign RSA OV SSL CA 2018"
#define CAMPUS_CERT_SUBJECT     "CN=*.campus.example.edu, O=Xidian University"
