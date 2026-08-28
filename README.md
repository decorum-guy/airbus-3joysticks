# Airbus 3 Joysticks

Turn ordinary gamepads into a compact Airbus A320neo home-cockpit control panel for Microsoft Flight Simulator 2020.

## Current status

The project is now a **two-controller flight-usable MVP**. LEFT and RIGHT are active by default; the complete CENTER / EFIS / RADIO profile remains preserved behind a feature flag until a third controller is available.

Validated on the tested MSFS 2020 A320neo setup:

- persistent LEFT / RIGHT identity by hardware serial;
- circular thumbstick motion -> virtual rotary detents;
- SPEED increment/decrement;
- HEADING increment/decrement;
- ALTITUDE increment/decrement;
- V/S increment (decrement has one final focused validation probe);
- SimConnect reconnecting event bridge;
- live FCU telemetry in the browser;
- Bluetooth PS4-compatible rumble using SDL GameController with extended reports;
- separate haptic intensity for rotary detents and warning cues;
- live LAN dashboard with stick position, pressed buttons, device status and readiness.

Exact Airbus-specific FCU PUSH/PULL, AP1/AP2, A/THR, SPD/MACH, TRK/FPA and some EFIS functions are intentionally still `pending` until their aircraft-specific backend is verified. The app never substitutes a plausible-but-wrong generic event for these controls.

## Physical layout

### LEFT · FCU SPD / HDG

- left stick circular rotation -> SPEED
- right stick circular rotation -> HEADING
- stick clicks and L1+stick clicks are reserved for exact Airbus PUSH/PULL
- face/D-pad buttons contain AP/LOC/APPR and pending Airbus-specific functions

### RIGHT · FCU ALT / V/S

- left stick circular rotation -> ALTITUDE
- right stick circular rotation -> V/S
- D-pad -> flaps / speedbrake
- face buttons -> spoiler arm / autobrake functions

### CENTER · EFIS / RADIO

The full profile is kept in config but is disabled by default. It can be enabled later without redistributing its functions onto LEFT or RIGHT.

## Install on Windows

Requirements:

- Windows 10/11 x64
- Microsoft Flight Simulator 2020
- Python 3.12 x64 recommended
- two currently active controllers connected

Clone the repository:

```powershell
git clone https://github.com/decorum-guy/airbus-3joysticks.git
cd airbus-3joysticks
```

Then simply run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

`run.ps1` is self-bootstrapping: if `.venv` does not exist, it runs `scripts/setup.ps1` automatically.

## Normal flight workflow

1. Start MSFS 2020 and load the tested A320neo into the cockpit.
2. Connect the LEFT and RIGHT controllers.
3. Run `scripts/run.ps1`.
4. Open the dashboard printed in the terminal.
5. Wait for **READY TO FLY**.
6. Rotate the sticks around their outer circle to change FCU targets.

The service deliberately drops control events while SimConnect is offline rather than replaying stale knob turns after reconnect.

## Browser pages

The service binds to `0.0.0.0:8765` by default.

- `/` — live cockpit dashboard
- `/haptics` — detent/warning rumble intensity and test controls
- `/editor` — persistent binding editor
- `/api/preflight` — machine-readable readiness state
- `/health` — service health + readiness

The dashboard shows:

- current SimConnect connection and aircraft title;
- live selected SPD / HDG / ALT / V/S telemetry;
- LEFT/RIGHT online state and serial identity;
- live thumbstick position/radius/angle;
- pressed buttons;
- current binding labels and pending markers;
- last dispatched action;
- detected SDL devices.

The web UI has no authentication. Use LAN access only on a trusted private network.

## Haptics

The tested PS4-compatible controllers expose two rumble motors through SDL when PS4 Bluetooth extended reports are enabled.

The project uses physically different profiles:

- **Changing values** — short, crisp pulse dominated by the high-frequency motor;
- **Warnings** — heavier pulse dominated by the low-frequency motor.

Overall strength remains independently adjustable for both channels at `/haptics`.

Real aircraft warning signals (Master Warning / Master Caution / stall cue, etc.) are a later aircraft-data integration layer; the warning haptic channel and test UI already exist.

## Controller identity

Identity preference:

1. hardware serial;
2. SDL device path;
3. GUID + VID/PID/name fallback.

The two currently tested controllers expose distinct stable serials and survived disconnect/reconnect identity testing. A fallback identifier is never presented as if it were a real hardware serial.

Config is stored at:

```text
%APPDATA%\Airbus3Joysticks\config.json
```

Diagnostic archives are stored under:

```text
%APPDATA%\Airbus3Joysticks\diagnostics\
```

## Circular stick rotary model

The rotary engine uses:

- inner reset radius;
- outer arm radius;
- `atan2(-y, x)` angle;
- wrap-safe angular delta;
- accumulated angular travel;
- discrete detents;
- reset on return to center.

Default values:

- inner radius: `0.32`
- outer radius: `0.58`
- detent angle: `22.5°`
- clockwise: increment
- counter-clockwise: decrement

Returning a stick to center resets angle tracking, preventing a jump when it is moved out again.

## Focused validation tools

Full controller diagnostics:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\diagnostics.ps1
```

FCU focused probe:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\fcu-probe.ps1
```

PS4 rumble probe:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\rumble-probe.ps1
```

Final V/S decrement probe:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\vs-dec-probe.ps1
```

See `docs/FCU_VALIDATION.md` for the measured FCU validation matrix.

## Architecture

```text
LEFT / RIGHT gamepads
        |
        v
SDL2 controller backend
  identity + axes + buttons + rumble
        |
        v
persistent role resolver
        |
        +--> button/combo router
        |
        +--> circular-stick rotary engine
        |          |
        |          v
        |      detent haptics
        |
        v
SimConnect bridge thread
  safe event queue + reconnect
  live FCU telemetry reads
        |
        v
MSFS 2020 A320neo

FastAPI / WebSocket
  live dashboard
  haptics settings/tests
  binding editor
  health/preflight API
```

## What remains after the core MVP

The remaining work is mostly aircraft-specific rather than controller/runtime work:

1. validate `AP_VS_VAR_DEC` with the focused probe;
2. implement verified A320-specific FCU PUSH/PULL;
3. implement AP1 / AP2 / A/THR and SPD/MACH / TRK-FPA through the verified aircraft backend;
4. implement CENTER EFIS/RADIO actions when the third controller returns;
5. connect real Master Warning / Master Caution / other warning data to the warning haptic channel;
6. optional tray/autostart and standalone `.exe` packaging;
7. optional rotary acceleration/per-control tuning after real flight use.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m airbus3j
```

CI runs on both Windows and Ubuntu for every pull request and on pushes to `main`.
