// RemoteACApp.h — Shared application entry points for Remote AC Controller.
// Used by both PlatformIO (agent-platformio) and Arduino IDE builds.
#ifndef REMOTE_AC_APP_H
#define REMOTE_AC_APP_H

#ifdef __cplusplus
extern "C" {
#endif

/// Call once during setup(). Initialises sensors, IR module, networking, and cloud.
void appSetup(void);

/// Call repeatedly during loop(). Runs the main control loop.
void appLoop(void);

#ifdef __cplusplus
}
#endif

#endif // REMOTE_AC_APP_H
