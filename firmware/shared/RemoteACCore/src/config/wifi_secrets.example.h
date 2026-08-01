#pragma once
/*
 * wifi_secrets.example.h — template for local WPA/WPA2 Wi-Fi credentials.
 *
 * HOW TO USE
 * ----------
 *   1. Copy this file to wifi_secrets.h in the SAME directory:
 *        cd firmware/shared/RemoteACCore/src/config
 *        cp wifi_secrets.example.h wifi_secrets.h
 *   2. Replace the placeholders below with your own router SSID and password.
 *   3. Build with ENABLE_WIFI_CREDENTIALS=1 and ENABLE_AUTO_WIFI_CONNECT=1
 *      (or connect manually with the `wifi connect` serial command).
 *
 * SECURITY
 * --------
 *   - wifi_secrets.h is git-ignored and must NEVER be committed.
 *   - Only the .example.h template may live in the repository.
 *   - Do not put the password in platformio.ini, build_flags, the serial
 *     console, terminal history, or CI logs.
 *   - These are HOME/LAB router credentials. Campus Xidian Wi-Fi is an OPEN
 *     SSID: its username/password belong in campus_secrets.h for the srun
 *     portal — they are NOT WiFi credentials and vice versa.
 */

#define LOCAL_WIFI_SSID     "your_wifi_name"
#define LOCAL_WIFI_PASSWORD "your_wifi_password"
