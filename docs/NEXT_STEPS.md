# Next implementation steps

1. Keep `AP_SPD_VAR_INC/DEC` for the production SPD rotary. The apparent 140→101 jump in the focused probe was explained by a manual cockpit change from 140 to 100 between the baseline snapshot and scripted increments; the events then correctly produced 101→105 and restored to 100. The earlier active probe also cleanly produced 140→141→140.
2. Run a focused V/S decrement test before declaring counter-clockwise V/S production-safe.
3. Use SDL GameController rumble as the primary haptics backend with PS4 Bluetooth extended reports enabled. Both controllers physically passed combined, low-motor-only and high-motor-only tests; SDL Joystick rumble is a verified fallback. The legacy SDL Haptic API is unsupported on these devices and should not be used.
4. Tune the haptics panel around two independent channels: short value-change detent feedback and higher-priority warning feedback. Because both motors were independently verified, consider separate motor mixes/patterns in addition to intensity.
5. Run an end-to-end live-stick test: circular stick detents → SimConnect/A320 action → visible FCU change → haptic tick.
