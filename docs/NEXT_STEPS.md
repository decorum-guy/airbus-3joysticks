# Next implementation steps

The two-controller controller/runtime core is validated end-to-end. Remaining work is now mostly aircraft-specific integration and product packaging.

1. Identify the exact installed A320 implementation before promoting any aircraft-specific button binding. `scripts/aircraft-identify.ps1` records SimConnect identity plus local package / manifest metadata and classifies known legacy Asobo, FlyByWire and iniBuilds families.
2. Validate the legacy/default Asobo A320neo FCU PUSH/PULL path when that family is detected. The aircraft-aware button probe uses the Asobo AUTOPILOT ModelBehavior B-events (with their documented external H-event fallbacks) instead of the previously tested FlyByWire-style `A320_Neo_FCU_*_PUSH/PULL` candidates.
3. Promote only physically confirmed PUSH/PULL actions to production bindings, then resolve AP1 / AP2 / A/THR / SPD-MACH / TRK-FPA and the other pending LEFT/RIGHT buttons for the detected aircraft family.
4. Validate LOC/APPR through the standard simulator events in a meaningful navigation/approach state. The earlier `A320_Neo_FCU_LOC_PUSH` / `A320_Neo_FCU_APPR_PUSH` H-event candidates were definite no-ops on `A320neo Global Livery` and must not be promoted.
5. Connect real aircraft warning state (Master Warning, Master Caution, and selected additional warning cues) to the already-implemented warning haptic channel and define priority/pattern rules.
6. When a third controller is available, enable the preserved CENTER profile and validate EFIS/RADIO actions.
7. Product polish: Windows tray/autostart, graceful background operation, and standalone executable packaging so normal use does not require a terminal or Python setup.

Validated core:

- SPD / HDG / ALT / V/S rotary directions: both directions validated in the cockpit.
- precision-first adaptive rotary response with hard no-backlog event-rate limiter: flight-tested.
- per-control rotary precision sliders and Reset defaults: implemented and persistent in AppData.
- persistent LEFT/RIGHT controller identity: validated across reconnects.
- SimConnect runtime bridge and live panel: validated.
- haptics: SDL GameController rumble with PS4 Bluetooth extended reports, SDL Joystick fallback; both low and high motors physically verified on both controllers.
- MobiFlight WASM transport: physically validated (`MF.Ping` -> `MF.Pong`) on the tested simulator installation.

Current aircraft evidence:

- SimConnect TITLE is `A320neo Global Livery`.
- This title matches the legacy/default Asobo A320neo naming family with high confidence; disk-level package identification is still used as the authoritative confirmation when available.
- The first aircraft-specific probe successfully transported every command through MobiFlight but produced definite no-ops for V/S PUSH, SPD/MACH, LOC and APPR, showing that transport health and aircraft-event compatibility are separate concerns.
