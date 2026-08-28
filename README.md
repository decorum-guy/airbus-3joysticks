# Airbus 3 Joysticks

Turn ordinary gamepads into a compact Airbus A320neo home-cockpit control panel for Microsoft Flight Simulator 2020.

## Current status

The project is now a **two-controller FlyByWire A32NX flight-ready MVP**. LEFT and RIGHT are active by default; the complete CENTER / EFIS / RADIO profile remains preserved behind a feature flag until a third controller is available.

Validated on the current MSFS 2020 + FlyByWire A32NX setup:

- persistent LEFT / RIGHT identity by hardware serial;
- circular thumbstick motion -> virtual rotary detents;
- SPEED / HEADING / ALTITUDE / V/S increment and decrement;
- per-control persistent rotary sensitivity from the browser, with reset-to-default controls;
- FlyByWire A32NX SPD / HDG / ALT / V/S PUSH and PULL;
- FlyByWire A32NX SPD/MACH and HDG/TRK · V/S/FPA toggles;
- FlyByWire A32NX AP1 / AP2 / A/THR / LOC / APPR button events;
- SimConnect reconnecting event bridge;
- live FCU telemetry in the browser;
- Bluetooth PS4-compatible rumble using SDL GameController with extended reports;
- separate haptic intensity for rotary detents and warning cues;
- live LAN dashboard with stick position, pressed buttons, device status and readiness.

FlyByWire custom events are **aircraft guarded**. The runtime identifies the current SimConnect aircraft title and refuses to send any `A32NX.*` event while another aircraft is loaded. Generic rotaries/flaps/spoilers may still work on other aircraft, but the dashboard marks the aircraft backend as generic-only.

## Physical layout

### LEFT · FCU SPD / HDG

- left stick circular rotation -> SPEED
- L3 -> SPD PUSH / managed
- L1 + L3 -> SPD PULL / selected
- right stick circular rotation -> HEADING
- R3 -> HDG PUSH / managed NAV
- L1 + R3 -> HDG PULL / selected
- □ / X -> AP1
- ○ / B -> AP2
- × / A -> A/THR
- △ / Y -> APPR
- D-pad left -> LOC
- D-pad up -> SPD / MACH
- D-pad down -> HDG/TRK · V/S/FPA toggle

### RIGHT · FCU ALT / V/S

- left stick circular rotation -> ALTITUDE
- L3 -> ALT PUSH / managed
- L1 + L3 -> ALT PULL / open climb/descent
- right stick circular rotation -> V/S
- R3 -> V/S PUSH / level off
- L1 + R3 -> V/S PULL / selected V/S
- D-pad -> flaps / speedbrake
- face buttons -> spoiler arm / autobrake functions

### CENTER · EFIS / RADIO

The full profile is kept in config but is disabled by default. It can be enabled later without redistributing its functions onto LEFT or RIGHT.

## Install on Windows

Requirements:

- Windows 10/11 x64
- Microsoft Flight Simulator 2020
- FlyByWire A32NX Stable for the full aircraft-specific control set
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

At startup, the app safely promotes old `pending` Airbus-specific bindings in an existing config to the FlyByWire production profile. Device assignments, haptics, sensitivity settings and custom user bindings are preserved. A custom binding is never overwritten merely because a built-in production action exists for the same physical button.

## Normal flight workflow

1. Start MSFS 2020 and load **FlyByWire A32NX** into the cockpit.
2. Wait until the aircraft cockpit has finished loading.
3. Connect the LEFT and RIGHT controllers.
4. Run `scripts/run.ps1`.
5. Open the dashboard printed in the terminal.
6. Wait for the controllers + SimConnect readiness indication.
7. Confirm the extra aircraft-backend pill says **A32NX · FULL CONTROLS**.
8. Use the sticks/buttons normally.

The service deliberately drops control events while SimConnect is offline rather than replaying stale knob turns after reconnect. It also blocks A32NX-only commands when the wrong aircraft is loaded.

## Browser pages

The service binds to `0.0.0.0:8765` by default.

- `/` — live cockpit dashboard
- `/haptics` — detent/warning rumble intensity and test controls
- `/editor` — persistent binding editor
- `/api/preflight` — machine-readable readiness state
- `/health` — service health + readiness

The dashboard shows:

- current SimConnect connection and aircraft title;
- live aircraft-backend state (`A32NX · FULL CONTROLS` or generic-only);
- live selected SPD / HDG / ALT / V/S telemetry;
- LEFT/RIGHT online state and serial identity;
- live thumbstick position/radius/angle;
- per-control sensitivity sliders and reset buttons;
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

Real FlyByWire warning signals (Master Warning / Master Caution / selected additional cues) are the next aircraft-data integration layer; the warning haptic channel and test UI already exist.

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

Per-control rotary sensitivity is stored separately at:

```text
%APPDATA%\Airbus3Joysticks\rotary-sensitivity.json
```

Diagnostic archives are stored under:

```text
%APPDATA%\Airbus3Joysticks\diagnostics\
```

## Circular stick rotary model

The rotary engine uses:

- inner reset radius;
- outer arm radius;
- wrap-safe `atan2(-y, x)` angular tracking;
- accumulated angular travel;
- precision-first slow response and bounded fast response;
- no queued/backlog turns after the user stops moving the stick;
- reset on return to center.

Default browser precision multipliers:

- SPEED: `1.00x`
- HEADING: `1.00x`
- ALTITUDE: `1.35x`
- V/S: `2.00x`

A larger multiplier means more physical stick travel is required for one logical FCU change, so the control is slower and easier to set precisely. Each control can be tuned live from the dashboard and reset independently to the defaults above.

## Aircraft-specific backend

The current full-control backend targets **FlyByWire A32NX** and uses its published custom SimConnect event namespace.

Production events include:

- `A32NX.FCU_SPD_PUSH` / `A32NX.FCU_SPD_PULL`
- `A32NX.FCU_HDG_PUSH` / `A32NX.FCU_HDG_PULL`
- `A32NX.FCU_ALT_PUSH` / `A32NX.FCU_ALT_PULL`
- `A32NX.FCU_VS_PUSH` / `A32NX.FCU_VS_PULL`
- `A32NX.FCU_SPD_MACH_TOGGLE_PUSH`
- `A32NX.FCU_TRK_FPA_TOGGLE_PUSH`
- `A32NX.FCU_AP_1_PUSH` / `A32NX.FCU_AP_2_PUSH`
- `A32NX.FCU_ATHR_PUSH`
- `A32NX.FCU_LOC_PUSH`
- `A32NX.FCU_APPR_PUSH`

The runtime performs an aircraft-family check before dispatching these actions, and the SimConnect bridge performs a second defensive check before queueing any `A32NX.*` event.

## Diagnostics

Aircraft identity:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\aircraft-identify.ps1
```

FlyByWire button probe:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\flybywire-button-probe.ps1
```

Full controller diagnostics:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\diagnostics.ps1
```

PS4 rumble probe:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\rumble-probe.ps1
```

The older stock-Asobo probes are kept for diagnostics/history, but the normal production profile is FlyByWire A32NX.

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
        |      |
        |      +--> guarded FlyByWire A32NX events
        |
        +--> circular-stick rotary engine
        |          |
        |          v
        |      detent haptics
        |
        v
SimConnect bridge thread
  aircraft-family safety gate
  safe event queue + reconnect
  live FCU telemetry reads
        |
        v
MSFS 2020 + FlyByWire A32NX

FastAPI / WebSocket
  live dashboard
  per-control rotary sensitivity
  aircraft backend status
  haptics settings/tests
  binding editor
  health/preflight API
```

## What remains after the flight-ready MVP

1. connect FlyByWire Master Warning / Master Caution / selected warning data to the warning haptic channel;
2. expose more managed/selected/AP/LOC/APPR state in the dashboard;
3. implement CENTER EFIS/RADIO actions when the third controller returns;
4. continue optional real-flight sensitivity tuning;
5. add Windows tray/autostart and standalone `.exe` packaging.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m airbus3j
```

CI runs on both Windows and Ubuntu for every pull request and on pushes to `main`.
