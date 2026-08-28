# Coding Agent Prompt

You are the execution/coding agent for **Airbus 3 Joysticks**.

Repository: `decorum-guy/airbus-3joysticks`

Product owner wants to test the project on Windows with Microsoft Flight Simulator 2020 and the stock Airbus A320neo as soon as possible.

## Read first

Before changing code, inspect:

- `README.md`
- `docs/ARCHITECTURE.md`
- current `main`
- all files under `src/airbus3j/`
- tests

Do not rewrite the project from scratch unless the existing approach is demonstrably broken.

## Current architectural decisions

- Windows host runs the controller service.
- Python 3.12 is the development runtime.
- PySDL2 + packaged SDL2 is the controller/input layer.
- Three persistent physical roles: `left`, `center`, `right`.
- Device identity priority: real SDL hardware serial -> SDL device path -> conservative fallback.
- Two analog sticks per controller may work as circular virtual rotary encoders.
- Returning a stick to center must never generate a value jump.
- Standard simulator actions use a dedicated SimConnect worker.
- Stale input must be dropped while SimConnect is offline, never replayed after reconnection.
- Airbus-specific actions must be a separate backend, preferably MobiFlight WASM ClientData / verified stock-A320 InputEvents or RPN.
- FastAPI serves a live LAN controller map on port 8765.
- Browser changes to bindings persist and appear live without reload.
- The web panel is not allowed to be required for flight-control processing.

## Non-negotiable safety/quality rule

**Do not invent A320neo event names or assume that generic AP events are equivalent to Airbus PUSH/PULL controls.**

If an exact stock-MSFS-2020 A320neo control path is not verified from source, documentation, an inspected MobiFlight/HubHop preset, or a direct simulator test, leave the binding explicitly `pending` and document what remains unknown.

## Immediate task

Bring the repository from baseline to a reliable first-flight MVP and verify as much as can be verified without access to the owner's physical Windows machine.

### 1. Audit the baseline before editing

Look for:

- PySDL2 API mistakes or version incompatibilities;
- controller hot-plug behavior;
- serial/path identity bugs;
- duplicated-controller ambiguity;
- asyncio/thread races;
- FastAPI route conflicts;
- malformed starter SimConnect event names;
- packaging/static-file mistakes;
- controller button mapping mistakes between SDL logical A/B/X/Y and PlayStation glyphs;
- dead-zone / clockwise-direction errors;
- cases where a combo could also fire its base action;
- accidental repeated events from noisy input.

Fix concrete problems you find.

### 2. Make the baseline testable without MSFS hardware

Add deterministic tests for at least:

- rotary CW / CCW direction;
- 359°/0° angle wrapping;
- inner/outer dead-zone hysteresis;
- no detent on initial arm;
- reset after centering;
- multiple detents from a sufficiently large angular move;
- combo precedence (`L1+L3` must not also fire `L3`);
- ambiguous identical-device fallback must not silently choose one;
- config persistence;
- pending actions never emit SimConnect traffic.

Where appropriate, introduce interfaces/fakes instead of monkey-patching global state.

### 3. Verify the standard SimConnect first-flight controls

For the stock MSFS 2020 A320neo, validate the baseline events used for:

- FCU SPEED increment/decrement;
- HEADING increment/decrement;
- ALTITUDE increment/decrement;
- V/S increment/decrement;
- BARO increment/decrement and STD;
- flaps one detent up/down;
- spoilers increase/decrease/arm;
- autobrake LOW/MED;
- APPR / LOC where applicable.

If a generic documented event exists but does not behave correctly on the stock A320neo, replace it with a verified aircraft-specific mechanism or mark it pending. Do not preserve a wrong event just because it is documented generically.

### 4. Implement the Airbus-specific action backend

Preferred path: MobiFlight WASM module ClientData communication from our own SimConnect client.

The MobiFlight WASM module provides command/response/LVar client data areas and supports executing gauge calculator/RPN code. Use its documented external-client protocol; register a unique client name for this application rather than taking over MobiFlight's default channels.

Implement this behind a clean action type such as:

```json
{
  "type": "mobiflight_rpn",
  "code": "...verified RPN..."
}
```

or a more specific verified input-event action type if that is more appropriate.

Required stock A320neo controls to investigate and implement where verified:

- SPD PUSH (managed) / PULL (selected)
- HDG PUSH / PULL
- ALT PUSH / PULL
- V/S PUSH / PULL
- AP1
- AP2
- A/THR
- SPD/MACH
- TRK/FPA
- EFIS ND range
- EFIS ND mode
- CSTR
- WPT
- VOR D
- ARPT

Keep per-aircraft details out of the generic controller/rotary engine.

### 5. Improve controller identity and setup UX

The owner may connect two identical PlayStation controllers plus one Xbox-style controller.

Requirements:

- display a real serial only when SDL actually exposes one;
- otherwise display that serial is unavailable and show the path/fallback identity separately;
- persisted assignments should survive normal restarts/reconnects when the OS identity permits;
- if identity becomes ambiguous, require press-a-button reassignment instead of guessing;
- assignment should clearly show which physical device was captured;
- do not allow the same physical controller to occupy two roles simultaneously.

### 6. Keep/improve the live LAN control map

The owner wants to put a MacBook next to the simulator and open the live scheme there.

The page should:

- show LEFT / CENTER / RIGHT in physical order;
- show online/offline status;
- show controller model;
- show serial if real, otherwise the identity fallback explicitly;
- visually show both sticks, L3/R3, L1/R1, D-pad and face buttons;
- display current labels around/on the controller schematic;
- update immediately when bindings change;
- visibly distinguish `pending` controls;
- show SimConnect/MobiFlight connectivity;
- show the last triggered control/action;
- remain usable on a 13–16 inch laptop screen.

A browser-rendered SVG/CSS diagram is acceptable and preferred for the live view. Literal PNG export is optional, not a blocker.

### 7. Add rotary tuning that is useful in flight

Do not overcomplicate before basic behavior is reliable.

After correctness, add configurable per-binding tuning if justified:

- detent degrees;
- invert direction;
- optional acceleration;
- max burst guard;
- rumble tick strength/duration.

Acceleration must never make a small correction unpredictably jump thousands of feet. Add tests.

### 8. Windows first-run quality

Keep the setup path very simple:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\scripts\run.ps1
```

Improve error messages for:

- Python missing/wrong architecture;
- SDL init failure;
- no controllers;
- MSFS not running;
- MobiFlight WASM missing when a MobiFlight action is attempted;
- Windows Firewall/LAN page inaccessible.

Do not require the full MSFS SDK just to run the application unless absolutely necessary.

### 9. Packaging only after functional verification

If the baseline is stable, prepare (or document) a standalone Windows `.exe` build, but do not let packaging work delay controller/MSFS correctness.

## Default physical layout to preserve unless evidence suggests a better one

### LEFT PlayStation controller

- left circular stick: FCU SPEED
- L3: SPD PUSH
- L1 + L3: SPD PULL
- right circular stick: FCU HEADING
- R3: HDG PUSH
- L1 + R3: HDG PULL
- face/D-pad: AP/LOC/APPR/FCU mode controls as verified

### CENTER Xbox-style controller

- left circular stick: BARO/QNH
- L3: BARO STD
- right circular stick: COM/radio utility once implemented correctly
- R3: COM swap
- D-pad: ND range/mode
- face buttons: CSTR/WPT/VOR D/ARPT
- unreliable shoulder buttons should not contain critical actions

### RIGHT PlayStation controller

- left circular stick: FCU ALTITUDE
- L3: ALT PUSH
- L1 + L3: ALT PULL
- right circular stick: V/S
- R3: V/S PUSH/level-off
- L1 + R3: V/S PULL
- D-pad: flaps and speedbrake
- face buttons: spoilers arm / autobrake controls as verified

## Deliverables

Work on a normal feature branch; do not force-push.

Before opening the PR:

1. run tests;
2. inspect the full diff;
3. remove debug hacks/dead code;
4. update README with exact Windows test instructions;
5. list what is verified versus what remains pending;
6. include a concise manual test checklist for the owner.

The PR summary must explicitly state:

- what can be tested today;
- what the owner must install;
- whether MobiFlight is required for the tested subset;
- which A320 controls remain pending;
- any behavior that could not be verified without the physical Windows/MSFS setup.
