# Next implementation steps

The two-controller FCU/controller core and the FlyByWire A32NX aircraft-specific button backend are now production-ready for the current setup.

Validated / promoted core:

- SPD / HDG / ALT / V/S rotary directions in both directions;
- browser-adjustable per-control rotary precision with persistent settings and reset defaults;
- persistent LEFT / RIGHT controller identity;
- SimConnect reconnecting bridge and live FCU telemetry;
- FlyByWire A32NX guarded production actions for SPD/HDG/ALT/V/S PUSH/PULL;
- FlyByWire A32NX SPD/MACH and TRK/FPA actions;
- FlyByWire A32NX AP1 / AP2 / A/THR / LOC / APPR actions;
- A32NX-specific events are blocked automatically when another aircraft is loaded;
- PS4 Bluetooth haptics with independent changing-values and warning channels.

Remaining work:

1. Connect real FlyByWire aircraft warning state (Master Warning, Master Caution, and selected additional warning cues) to the existing warning haptic channel and define priority/pattern rules.
2. Improve dashboard state telemetry for managed/selected FCU modes, AP1/AP2, A/THR, LOC/APPR and TRK/FPA so the browser mirrors more of the actual FCU state instead of only selected numeric targets.
3. When a third controller is available, enable the preserved CENTER profile and implement/validate FlyByWire EFIS/RADIO actions.
4. Continue real-flight tuning of the four persistent rotary sensitivity values if desired.
5. Product polish: Windows tray/autostart, graceful background operation, and standalone executable packaging so normal use does not require a terminal or Python setup.
