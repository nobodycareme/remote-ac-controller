# PubSubClient — Vendored Library Record

- **Library**: PubSubClient (MQTT client for Arduino)
- **Version**: 2.8
- **Author**: Nick O'Leary <nick.oleary@gmail.com>
- **Upstream URL**: https://github.com/knolleary/pubsubclient
- **License**: MIT (see LICENSE.txt)
- **Vendored Date**: 2026-07-18
- **Source**: Originally resolved by PlatformIO libdeps into .pio/libdeps/nodemcuv2/PubSubClient/
- **Reason**: mqtt_client.h includes <PubSubClient.h>; vendored to avoid network dependency resolution during builds (environment consolidation requirement)

## SHA256 (key source files)
- `src/PubSubClient.h`:  376ddb9ecda5816dfeff344f8742253d487adc16272455ebe2dfa4c071cdd348
- `src/PubSubClient.cpp`: c5ab036263d514791b1955fe44aacca103b2eea4ca07cd539bff25dd88cc4ede

## Notes
- No `lib_deps` entry in platformio.ini for PubSubClient — this vendored copy is the sole provider.
- This vendoring is for environment consolidation only; it does NOT constitute MQTT feature development.
