# Airbus 3 Joysticks

Turn three ordinary gamepads into a compact Airbus A320neo home-cockpit controller for Microsoft Flight Simulator 2020.

> Status: early MVP. The controller engine, persistent device roles, rotary-stick logic, local-network web panel, editable bindings and a standard SimConnect event bridge are being built first. Airbus-specific FCU push/pull and EFIS actions that need gauge/WASM access are intentionally isolated behind an action backend and are the next implementation step.

## Goal

Three physical controllers are placed **LEFT / CENTER / RIGHT**. The app remembers which physical device owns each role, reads their controls, converts circular stick motion into virtual rotary encoder detents, sends simulator actions to MSFS 2020, and serves a live visual control map over the local network.

Typical layout:

- **LEFT (DualSense):** FCU SPEED + HEADING, AP controls.
- **CENTER (Xbox-style):** BARO, EFIS, radio/utility controls.
- **RIGHT (DualSense):** FCU ALTITUDE + V/S, flaps, spoilers, autobrake.

The visual panel is served from the Windows PC so a MacBook/iPad/phone on the same LAN can show the current assignments. Changes made in the app are pushed to the page live over WebSocket; no page reload is required.

## MVP architecture

```text
DualSense LEFT  ─┐
Xbox CENTER     ─┼─> SDL2 input + identity
DualSense RIGHT ─┘        │
                           ├─> persistent LEFT/CENTER/RIGHT roles
                           │
                           ├─> button/combo engine
                           ├─> circular-stick rotary engine
                           │      dead-zone + angle unwrap + detents
                           │
                           ├─> action router
                           │      ├─ standard SimConnect events
                           │      └─ MobiFlight/WASM backend (next)
                           │
                           └─> FastAPI local web server
                                  ├─ REST config API
                                  ├─ WebSocket live state
                                  └─ SVG/CSS controller map
```

### Why SDL2

SDL2 exposes a game-controller abstraction as well as joystick serial numbers and implementation-dependent device paths on supported drivers. We persist identity in this order:

1. hardware serial, when SDL/driver exposes it;
2. SDL device path;
3. GUID + VID/PID/name fallback.

A fallback identifier is **not** treated or displayed as a real hardware serial.

### Why a web panel instead of generating a PNG every time

The panel is a live browser view. It is effectively the requested "picture with labels", but the labels can update instantly. It also scales correctly on a MacBook/iPad without regenerating image files. Static PNG/SVG export can be added later.

## Install on Windows

Requirements:

- Windows 10/11 x64
- Microsoft Flight Simulator 2020
- Python **3.12 x64** recommended
- the three controllers connected before first assignment

You **do not need the MSFS SDK** for the standard SimConnect MVP. `pysimconnect` ships a compatible SimConnect client DLL.

MobiFlight is **not required for the first rotary test**. It will be required for the Airbus-specific controls that cannot be expressed reliably as standard SimConnect key events (notably exact FCU push/pull and some EFIS/input-event actions).

### 1. Clone

```powershell
git clone https://github.com/decorum-guy/airbus-3joysticks.git
cd airbus-3joysticks
```

### 2. Bootstrap

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

This creates `.venv` and installs the Python dependencies.

### 3. Run

Start MSFS 2020 (a flight may already be loaded), then:

```powershell
.\scripts\run.ps1
```

The terminal prints two addresses:

- local: `http://127.0.0.1:8765`
- LAN: `http://<windows-ip>:8765`

Open the LAN address on the MacBook. Windows Firewall may ask whether Python may accept connections; allow it on **Private networks** if you want the MacBook page to work.

The web UI has no authentication in the MVP. Run it only on a trusted private LAN.

## First-run workflow

1. Open the web panel.
2. Click **Assign** on LEFT.
3. Press any normal button on the physical controller that is physically on the left.
4. Repeat for CENTER and RIGHT.
5. The role mapping is saved under `%APPDATA%\Airbus3Joysticks\config.json`.
6. Restarting the app reuses the saved identities.

If two identical controllers expose real serial numbers, those serials are used. If they do not, SDL device paths are used. If Windows changes a fallback path after reconnecting hardware, re-assignment may be required; the UI will show that the saved device is missing instead of silently assigning the wrong controller.

## Circular stick = rotary encoder

A rotary stick is armed only after its radius passes the configured outer dead-zone. The first angle becomes the reference point. While the stick stays outside the active radius, the engine unwraps `atan2(y, x)` across the 0/360-degree boundary and accumulates angular travel.

Every configured angular step emits one virtual detent. Returning the stick to the inner dead-zone resets tracking, so returning to center cannot generate a giant accidental change.

Default direction:

- clockwise = increment
- counter-clockwise = decrement

Default FCU mapping:

| Position | Stick | Function |
|---|---|---|
| LEFT | left | SPEED |
| LEFT | right | HEADING |
| RIGHT | left | ALTITUDE |
| RIGHT | right | V/S |
| CENTER | left | BARO |
| CENTER | right | COM/utility (Airbus-specific backend pending) |

## What is working in the first code baseline

- SDL2 controller discovery.
- Best-effort hardware serial and device-path identity.
- Persistent LEFT/CENTER/RIGHT assignment.
- Press-a-button device assignment mode.
- Standard game-controller buttons/axes.
- Circular-stick rotary detector with inner/outer dead-zones and angle unwrapping.
- Optional short rumble tick on rotary detents.
- Config persisted in `%APPDATA%\Airbus3Joysticks`.
- FastAPI web server on port 8765.
- REST state/config endpoints.
- WebSocket live updates.
- Browser controller map rendered as a live diagram.
- Standard SimConnect action queue with automatic reconnect attempts.
- Safe `noop`/pending actions for controls whose exact A320neo implementation has not yet been verified.

## Standard MSFS events used by the starter profile

The starter profile intentionally uses standard documented events for the first hardware test, including:

- `AP_SPD_VAR_INC` / `AP_SPD_VAR_DEC`
- `HEADING_BUG_INC` / `HEADING_BUG_DEC`
- `AP_ALT_VAR_INC` / `AP_ALT_VAR_DEC`
- `AP_VS_VAR_INC` / `AP_VS_VAR_DEC`
- `KOHLSMAN_INC` / `KOHLSMAN_DEC`
- `BAROMETRIC_STD_PRESSURE`
- `FLAPS_INCR` / `FLAPS_DECR`
- `SPOILERS_INC` / `SPOILERS_DEC`
- `SPOILERS_ARM_TOGGLE`
- `AUTOBRAKE_LO_SET` / `AUTOBRAKE_MED_SET`

Exact A320neo FCU managed/selected PUSH/PULL semantics are deliberately **not guessed** in the starter profile.

## Project layout

```text
src/airbus3j/
  app.py               process orchestration
  config.py            persistent config + default profile
  controllers.py       SDL2 discovery, identity and input snapshots
  rotary.py            circular-stick detector
  runtime.py           role mapping, button/combo + rotary routing
  simconnect_bridge.py reconnecting SimConnect worker
  web.py               FastAPI/WebSocket API
  static/index.html    live visual controller panel + editor
scripts/
  setup.ps1
  run.ps1
docs/
  ARCHITECTURE.md
  CODER_PROMPT.md
```

## Binding model

A binding contains a human label and an action. This separation matters: the web panel can be useful even for actions that are not implemented yet.

Examples:

```json
{
  "trigger": "rotary:left",
  "label": "FCU SPEED",
  "clockwise": {"type": "sim_event", "event": "AP_SPD_VAR_INC"},
  "counter_clockwise": {"type": "sim_event", "event": "AP_SPD_VAR_DEC"}
}
```

```json
{
  "trigger": "leftshoulder+leftstick",
  "label": "SPD PULL",
  "action": {
    "type": "pending",
    "reason": "Requires verified A320neo selected-speed action"
  }
}
```

`pending` is intentional: a visible unimplemented binding is safer than sending a plausible-but-wrong flight-control event.

## Local network panel

The server binds to `0.0.0.0:8765` by default so another device on the LAN can open it. The page subscribes to `/ws` and receives state broadcasts when:

- a controller connects/disconnects;
- a role is assigned;
- a binding is edited;
- SimConnect connects/disconnects;
- the active input changes.

## Next milestones

1. Verify the starter profile against the exact MSFS 2020 stock A320neo version.
2. Implement MobiFlight WASM client-data transport as a second action backend.
3. Replace pending FCU PUSH/PULL with verified A320neo input events/RPN.
4. Add EFIS ND range/mode/filter actions.
5. Add DualSense touchpad gestures.
6. Improve rotary acceleration and per-control tuning.
7. Add tray app + optional Windows auto-start.
8. Package a standalone `.exe` so Python is no longer required.
9. Optional SVG/PNG snapshot endpoint for a literal generated control-map image.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m airbus3j
```

See `docs/ARCHITECTURE.md` and `docs/CODER_PROMPT.md` for the implementation contract and the next coding-agent task.
