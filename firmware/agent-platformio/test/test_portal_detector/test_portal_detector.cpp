// ============================================================
// test_portal_detector.cpp - offline captive-portal classification suite
// ============================================================
// Covers PortalDetector::classifyResponse(), the single source of truth for
// captive-portal detection shared by wifi_manager.cpp and the portal-probe
// firmware. Every fixture is desensitized and mirrors test/portal_fixtures/:
// no credentials, MAC addresses or tokens appear anywhere in this file.
//
// Execution model: this is an embedded (nodemcuv2) suite. Project policy
// forbids flashing hardware from the automation path, so `tools/dev.ps1 test`
// runs it with --without-uploading --without-testing, which compiles the suite
// together with the full production sources. That catches the class of defect
// this repository actually suffers from (broken conditional-compilation guards
// and link errors) without touching a device. Run it on real hardware with
// `pio test -e nodemcuv2` when a board is attached.

#include <Arduino.h>
#include <unity.h>

#include "network/portal_detector.h"

// ---- Fixture 01: 3xx redirect carrying ac_id in Location -------------------
void test_3xx_redirect_is_captive(void) {
    PortalResult r;
    const bool captive = PortalDetector::classifyResponse(
        302,
        String("http://") + CAMPUS_PORTAL_HOST + "/srun_portal_pc?ac_id=8&theme=basic",
        "text/html",
        "",
        r);

    TEST_ASSERT_TRUE_MESSAGE(captive, "3xx to the portal host must classify as captive");
    TEST_ASSERT_TRUE(r.captive);
    TEST_ASSERT_EQUAL_INT_MESSAGE(1, r.method, "method 1 == detected via 3xx Location");
    TEST_ASSERT_EQUAL_STRING("8", r.acId.c_str());
    // The query string may carry tokens and must never survive into the log.
    TEST_ASSERT_EQUAL_INT_MESSAGE(-1, r.portalUrl.indexOf('?'),
                                  "portalUrl must be sanitized of its query string");
}

// ---- Fixture 02: HTTP 200 transparent intercept, auto-submit form ----------
void test_200_autosubmit_form_is_captive(void) {
    PortalResult r;
    const String body =
        String("<html><body onload=\"document.forms[0].submit()\">"
               "<form method=\"post\" action=\"http://") + CAMPUS_PORTAL_HOST +
        "/srun_portal_pc?ac_id=8\"></form></body></html>";

    const bool captive = PortalDetector::classifyResponse(200, "", "text/html", body, r);

    TEST_ASSERT_TRUE_MESSAGE(captive, "200 intercept page must classify as captive");
    TEST_ASSERT_EQUAL_INT_MESSAGE(2, r.method, "method 2 == detected via 200 intercept body");
    TEST_ASSERT_EQUAL_STRING("8", r.acId.c_str());
}

// ---- Fixture 02b: meta-refresh to srun_portal_pc, no host literal ----------
// Real-world campus shape: the body never spells out the portal host, only the
// srun_portal_pc path. A host-literal-only matcher would regress here.
void test_200_metarefresh_srunportal_is_captive(void) {
    PortalResult r;
    const String body =
        "<html><head><meta http-equiv=\"refresh\" "
        "content=\"0;url=/srun_portal_pc?ac_id=8&theme=basic\"></head></html>";

    const bool captive = PortalDetector::classifyResponse(200, "", "text/html", body, r);

    TEST_ASSERT_TRUE_MESSAGE(captive, "meta-refresh to srun_portal_pc must classify as captive");
    TEST_ASSERT_EQUAL_STRING_MESSAGE("8", r.acId.c_str(), "ac_id must be parsed from the body");
}

// ---- Fixture 03: HTTP 204 -> already online --------------------------------
void test_204_is_already_online(void) {
    PortalResult r;
    const bool captive = PortalDetector::classifyResponse(204, "", "", "", r);

    TEST_ASSERT_FALSE_MESSAGE(captive, "204 No Content means the device is already online");
    TEST_ASSERT_EQUAL_INT_MESSAGE(3, r.method, "method 3 == already-online");
}

// ---- Fixture 04: plain 200 page, no campus markers -------------------------
void test_plain_200_is_not_captive(void) {
    PortalResult r;
    const bool captive = PortalDetector::classifyResponse(
        200, "", "text/html", "<html><body><h1>hello</h1></body></html>", r);

    TEST_ASSERT_FALSE_MESSAGE(captive, "an ordinary 200 page is not a captive portal");
}

// ---- Fixture 05: transport failure -----------------------------------------
// A failed GET is "unknown", never "captive": guessing here would drive the
// state machine into an authentication attempt on a healthy network.
void test_network_failure_is_not_captive(void) {
    PortalResult r;
    TEST_ASSERT_FALSE(PortalDetector::classifyResponse(-1, "", "", "", r));
    TEST_ASSERT_FALSE(PortalDetector::classifyResponse(0, "", "", "", r));
}

// ---- Aggregate: the embedded fixture table shipped with the module ---------
void test_embedded_unit_test_table_passes(void) {
    TEST_ASSERT_TRUE_MESSAGE(PortalDetector::unitTest(),
                             "PortalDetector::unitTest() embedded fixtures must all classify");
}

void setUp(void) {}
void tearDown(void) {}

void runAllTests(void) {
    UNITY_BEGIN();
    RUN_TEST(test_3xx_redirect_is_captive);
    RUN_TEST(test_200_autosubmit_form_is_captive);
    RUN_TEST(test_200_metarefresh_srunportal_is_captive);
    RUN_TEST(test_204_is_already_online);
    RUN_TEST(test_plain_200_is_not_captive);
    RUN_TEST(test_network_failure_is_not_captive);
    RUN_TEST(test_embedded_unit_test_table_passes);
    UNITY_END();
}

void setup() {
    // Give the USB CDC/UART a moment before Unity starts emitting results.
    delay(2000);
    runAllTests();
}

void loop() {}
