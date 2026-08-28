# Next implementation steps

1. Replace the production SPD rotary binding with a verified A320-specific transport. The generic `AP_SPD_VAR_INC/DEC` path is rejected by the focused 2026-08-28 hardware/simulator probe because the first increment jumped the target from 140 kt to 101 kt and restore ended at 100 kt.
2. Run a focused V/S decrement test before declaring counter-clockwise V/S production-safe.
3. Complete the PS4/DualShock-compatible rumble transport probe and select the first physically verified backend for the haptics panel.
4. Only after the above, run an end-to-end live-stick test: circular stick detents → SimConnect/A320 action → visible FCU change → haptic tick.
