# Next implementation steps

The controller/runtime MVP is now substantially complete. Remaining work is mostly aircraft-specific or packaging polish.

1. Run `scripts/vs-dec-probe.ps1` and validate `AP_VS_VAR_DEC` for counter-clockwise V/S.
2. Perform one end-to-end cockpit smoke test with the production service: circular stick detent -> visible FCU change -> crisp haptic tick, for SPD / HDG / ALT / V/S.
3. Implement a verified stock-A320-specific backend for FCU PUSH/PULL. Do not guess generic events for managed/selected semantics.
4. Through that verified backend, add AP1 / AP2 / A/THR / SPD-MACH / TRK-FPA and any other currently pending LEFT/RIGHT buttons.
5. Connect real aircraft warning state (Master Warning, Master Caution, and selected additional warning cues) to the already-implemented warning haptic channel and define priority/pattern rules.
6. When a third controller is available, enable the preserved CENTER profile and validate EFIS/RADIO actions.
7. After real-flight use, optionally tune detent angle, per-control acceleration, and haptic durations.
8. Optional product polish: Windows tray/autostart and standalone executable packaging.

Validated haptic transport: SDL GameController rumble with PS4 Bluetooth extended reports, with SDL Joystick rumble as a verified fallback. Both low and high motors were physically verified independently on both active controllers.
