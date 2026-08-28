# Next implementation steps

The two-controller controller/runtime core is validated end-to-end. Remaining work is now mostly aircraft-specific integration and product packaging.

1. Ship and tune the precision-first adaptive rotary response: slow rotation for exact values, faster rotation for coarse changes, with a hard no-backlog event-rate limiter.
2. Implement a verified stock-A320-specific backend for FCU PUSH/PULL. Do not guess generic events for managed/selected semantics.
3. Through that verified backend, add AP1 / AP2 / A/THR / SPD-MACH / TRK-FPA and the other currently pending LEFT/RIGHT buttons.
4. Connect real aircraft warning state (Master Warning, Master Caution, and selected additional warning cues) to the already-implemented warning haptic channel and define priority/pattern rules.
5. Add browser-exposed rotary tuning once the new precision profile has been flight-tested, so slow/fast response can be adjusted without editing config files.
6. When a third controller is available, enable the preserved CENTER profile and validate EFIS/RADIO actions.
7. Product polish: Windows tray/autostart, graceful background operation, and standalone executable packaging so normal use does not require a terminal or Python setup.

Validated core:

- SPD / HDG / ALT / V/S rotary directions: both directions validated in the cockpit.
- persistent LEFT/RIGHT controller identity: validated across reconnects.
- SimConnect runtime bridge and live panel: validated.
- haptics: SDL GameController rumble with PS4 Bluetooth extended reports, SDL Joystick fallback; both low and high motors physically verified on both controllers.
