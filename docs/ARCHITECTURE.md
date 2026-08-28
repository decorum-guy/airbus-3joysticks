# Architecture

## Product contract

The application is a Windows-side controller service for MSFS 2020. It owns three physical gamepad roles (`left`, `center`, `right`), persists those roles across runs, converts circular analog-stick motion into rotary detents, routes button/combo inputs into simulator actions, and serves a live control map to browsers on the local network.

The browser is a view/editor; flight-control input must continue to work if no browser is open.

The current hardware phase can run with the CENTER role disabled by feature flag while preserving its profile and bindings for a future third wireless controller.

## Components

### `ConfigStore`

Persistent JSON under `%APPDATA%\Airbus3Joysticks\config.json`.

Responsibilities:
- roles and saved device identities;
- controller bindings and human labels;
- rotary tuning;
- web server settings.

Writes are atomic via temporary file + replace.

### `ControllerBackend`

PySDL2 over packaged SDL2 binaries.

Responsibilities:
- enumerate SDL GameController devices;
- obtain controller name, GUID, VID/PID, serial, path and instance ID;
- normalize standard game-controller axes/buttons;
- provide rumble output.

Identity priority:
1. serial;
2. path;
3. GUID + VID/PID + name + runtime instance fallback.

An SDL serial may be absent. Never label a fallback ID as a hardware serial.

### `Runtime`

Single asyncio control loop at ~60 Hz.

Responsibilities:
- resolve saved physical devices to LEFT/CENTER/RIGHT;
- press-any-button assignment flow;
- button edge detection;
- modifier combos, with the most specific combo winning over its unmodified subset;
- rotary updates;
- route actions;
- expose live state to the web server.

### `RotaryEngine`

For each `(device, stick)`:
1. idle inside inner dead-zone;
2. arm only after crossing outer radius;
3. store first angle without emitting a detent;
4. unwrap angle delta across ±π;
5. accumulate physical angular travel;
6. emit signed detents whenever accumulated travel crosses `detent_degrees`;
7. reset when the stick returns to inner dead-zone.

Public sign convention:
- `+N` = clockwise detents;
- `-N` = counter-clockwise detents.

No absolute stick angle is mapped to an absolute FCU value.

### `SimConnectBridge`

Owns SimConnect on a dedicated worker thread.

Rules:
- reconnect automatically while MSFS is not ready;
- never replay stale control events after a disconnect;
- drop input while offline and expose a dropped-event count;
- keep standard SimConnect event transport independent from Airbus-specific transport.

`pysimconnect` is used because it is a small MIT-licensed wrapper and ships a client DLL. Standard documented key events are sufficient for the first rotary test.

### Airbus action backend (next milestone)

Some A320neo controls are aircraft/gauge-specific. The next backend should use MobiFlight WASM ClientData communication (or another verified stock-A320 InputEvent path) for exact FCU/EFIS semantics.

Required actions include:
- SPD PUSH / PULL;
- HDG PUSH / PULL;
- ALT PUSH / PULL;
- V/S PUSH / PULL;
- AP1 and AP2 independently;
- A/THR pushbutton;
- SPD/MACH;
- TRK/FPA;
- EFIS ND range/mode and CSTR/WPT/VOR D/ARPT.

These are `pending` in the starter config until verified. A plausible but unverified event is not acceptable.

### Haptic cockpit alerts (future milestone)

Use controller rumble as an optional tactile annunciation layer once the relevant A320 state variables and acknowledgement events have been verified.

Potential outputs:
- a strong repeating pattern for Master Warning;
- a distinct lower-priority pattern for Master Caution;
- an optional continuous/repeating high-urgency vibration for stall warning / low-speed protection cues;
- additional carefully selected aircraft warnings only when the simulator exposes a trustworthy state signal.

Potential inputs:
- dedicated controller buttons or button combinations for Master Warning acknowledgement/reset;
- dedicated controller buttons or button combinations for Master Caution acknowledgement/reset.

This is an enhancement rather than a claim of physical A320 fidelity. The real A320 sidestick does not use a conventional mechanical stick shaker; any stall-related gamepad vibration is therefore a deliberate custom tactile cue.

Implementation requirements:
- warning patterns must be distinguishable by feel;
- alert rumble must take priority over the short rotary-detent tick;
- no warning state may be guessed from generic events alone;
- acknowledgement/reset actions remain `pending` until exact stock-A320 semantics are verified;
- provide per-alert enable/disable and strength settings because controller rumble strength varies significantly by hardware and connection mode.

### Web server

FastAPI binds to `0.0.0.0:8765` by default.

Endpoints:
- `GET /` live visual map;
- `GET /health` health/status;
- `GET /api/state` full public runtime state;
- `POST /api/assign/{role}` arm press-any-button assignment;
- `DELETE /api/assign/{role}` clear assignment;
- `PUT /api/bindings/{role}` replace and persist bindings;
- `WS /ws` live state frames.

The MVP has no authentication. It is for a trusted private LAN only.

## Binding schema

### Button

```json
{
  "trigger": "dpad_down",
  "label": "FLAPS one detent DOWN",
  "action": {"type": "sim_event", "event": "FLAPS_INCR"}
}
```

### Combo

```json
{
  "trigger": "leftshoulder+leftstick",
  "label": "SPD PULL · selected",
  "action": {"type": "pending", "reason": "Needs verified A320 action"}
}
```

### Rotary

```json
{
  "trigger": "rotary:left",
  "label": "FCU SPEED",
  "clockwise": {"type": "sim_event", "event": "AP_SPD_VAR_INC"},
  "counter_clockwise": {"type": "sim_event", "event": "AP_SPD_VAR_DEC"}
}
```

Supported action types in baseline:
- `sim_event`;
- `pending`;
- `noop`.

The action router is the extension point for `mobiflight_rpn` / `input_event` / radio helpers.

## Reliability invariants

1. Never silently swap two identical controllers when identity is ambiguous.
2. Never replay stale flight-control events after reconnect.
3. Returning a rotary stick to center must never emit a large change.
4. A modified button combo must not also fire the unmodified button action on the same edge.
5. Persist bindings/roles immediately after a successful edit/assignment.
6. The web panel may display unimplemented controls, but those controls must be explicitly marked pending.
7. Browser/network failure must not stop controller input processing.

## Packaging direction

Development: Python 3.12 + editable install.

Target: a Windows standalone executable (PyInstaller or Nuitka) with SDL2 binaries and static web assets bundled. Packaging should come after the hardware/MSFS event path is verified, not before.
