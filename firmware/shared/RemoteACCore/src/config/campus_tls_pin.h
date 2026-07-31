#pragma once
#include "config/campus_config.h"
/*
 * Campus portal TLS certificate pin.
 *
 * PUBLIC INFORMATION ONLY. A server certificate — and therefore its SHA-1
 * fingerprint, subject, issuer and validity window — is presented to every
 * client that opens a TLS connection to the portal. None of it is a secret and
 * none of it is a credential.
 *
 * SOURCING
 *   A pin describes one campus, so it is supplied by the campus profile
 *   selected through CAMPUS_PROFILE_HEADER (see config/campus_config.h), or by
 *   an external config.h / globals.h. This header only supplies the defaults.
 *
 * FAIL-CLOSED DEFAULT
 *   With no pin supplied, CAMPUS_CERT_SHA1 is the empty string.
 *   CampusAuthVendor::tlsPinValid() requires at least 40 characters, so an
 *   unpinned build REFUSES to authenticate: credentials are never transmitted
 *   over a channel whose server identity was not verified. There is deliberately
 *   no fallback to setInsecure().
 *
 * ENFORCEMENT
 *   The ESP8266 calls BearSSL::WiFiClientSecure::setFingerprint(CAMPUS_CERT_SHA1)
 *   before the portal handshake. If the server presents any other leaf
 *   certificate the handshake fails and login aborts with TLS_PIN_MISMATCH.
 *
 * ROTATION
 *   A pin expires with the certificate it identifies. Re-extract it over a
 *   trusted channel before CAMPUS_CERT_NOT_AFTER and update the profile — never
 *   auto-trust a certificate that changed:
 *
 *     openssl s_client -connect <host>:443 -servername <host> -showcerts \
 *       </dev/null 2>/dev/null | openssl x509 -noout -fingerprint -sha1 -dates
 *
 *   "Verify return code: 0 (ok)" must appear in the s_client output, otherwise
 *   the fingerprint may belong to an interception proxy rather than the portal.
 */

#ifndef CAMPUS_CERT_SHA1
#  define CAMPUS_CERT_SHA1       ""
#endif
#ifndef CAMPUS_CERT_NOT_BEFORE
#  define CAMPUS_CERT_NOT_BEFORE ""
#endif
#ifndef CAMPUS_CERT_NOT_AFTER
#  define CAMPUS_CERT_NOT_AFTER  ""
#endif
#ifndef CAMPUS_CERT_ISSUER
#  define CAMPUS_CERT_ISSUER     ""
#endif
#ifndef CAMPUS_CERT_SUBJECT
#  define CAMPUS_CERT_SUBJECT    ""
#endif
