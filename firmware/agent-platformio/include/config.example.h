// ============================================================
// config.example.h  -  TEMPLATE. Copy to config.h and edit.
// (config.h is git-ignored; do NOT commit real credentials.)
//
// This file is the single, authoritative credential TEMPLATE. Real values
// live ONLY in config.h (git-ignored). Do NOT introduce a second convention
// such as secrets.h / secrets.example.h in this project.
//
// Hardware pin assignments are NOT defined here — they live in
// include/config/hardware_config.h (single source of truth). Do not add
// DHT11_PIN / IR_UART_* / LED defines to this credential template.
// ============================================================
#ifndef CONFIG_EXAMPLE_H
#define CONFIG_EXAMPLE_H

// ----- Wi-Fi (example only; real values go in config.h) -----
#define EXAMPLE_WIFI_SSID     "YOUR_WIFI_SSID"
#define EXAMPLE_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// ----- Cloud / MQTT (example placeholders) -----
#define EXAMPLE_CLOUD_HOST "your-cloud.example.com"
#define EXAMPLE_CLOUD_PORT 1883
#define EXAMPLE_MQTT_USER  "device_user"
#define EXAMPLE_MQTT_PASS  "device_password"

#endif // CONFIG_EXAMPLE_H
