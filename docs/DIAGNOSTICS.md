# Guided diagnostics

Use this before deeper A320-specific development. It captures the facts that can only be observed on the real Windows PC with the physical controllers and MSFS 2020 running.

## Run

From PowerShell in the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\diagnostics.ps1
```

Do **not** run `scripts\run.ps1` at the same time.

If `.venv` is missing, the diagnostics launcher runs `scripts\setup.ps1` first.

## What the wizard records

1. SDL runtime version.
2. Every detected game controller:
   - name;
   - actual SDL hardware serial, if exposed;
   - SDL device path, if exposed;
   - GUID;
   - VID/PID;
   - identity source used by the app;
   - touchpad/sensor/rumble capability where SDL exposes it.
3. Human-confirmed LEFT / CENTER / RIGHT role assignment.
4. Optional but strongly recommended unplug/replug identity test for each role.
5. Input exercise for each controller:
   - min/max ranges for both sticks and both triggers;
   - every standardized button actually observed;
   - touchpad finger activity when SDL exposes it.
6. Short rumble test with human confirmation.
7. Optional SimConnect diagnostics against a loaded MSFS 2020 flight:
   - connection/import status;
   - aircraft TITLE / ATC MODEL where readable;
   - generic FCU-related SimVars before and after the operator manually changes the FCU with the mouse;
   - optional active one-step probes for SPD, HDG, ALT and V/S.

## Active SimConnect probe

The active probe does not run automatically. The wizard requires the literal input:

```text
ACTIVE
```

It then sends exactly one standard increment event at a time:

- `AP_SPD_VAR_INC`
- `HEADING_BUG_INC`
- `AP_ALT_VAR_INC`
- `AP_VS_VAR_INC`

For each probe it records the relevant SimVar before/after, asks whether the visible stock A320neo FCU target actually increased, then sends the matching decrement event as a best-effort restore.

Run this only when a small FCU target change is safe. It does **not** probe Airbus PUSH/PULL modes and does not pretend that generic SimConnect events are equivalent to Airbus managed/selected logic.

## Reconnect identity test

This test matters especially for two identical DualSense controllers.

For each role the wizard records identity before disconnect, while disconnected, and after reconnect, then classifies the result as one of:

- `stable_serial`
- `stable_path`
- `same_generated_key_without_serial_or_path`
- `identity_changed_or_unresolved`
- `could_not_uniquely_identify_reconnected_device`

A fallback identifier is never described as a hardware serial.

## Normal config

At the end of the controller tests the wizard can save the final human-confirmed LEFT/CENTER/RIGHT identities into the normal application config:

```text
%APPDATA%\Airbus3Joysticks\config.json
```

This means the later normal app launch can reuse the diagnostic assignment.

## Report

The wizard always tries to save two copies:

```text
<repository>\diagnostics-report.json
%APPDATA%\Airbus3Joysticks\diagnostics\diagnostics-YYYYMMDD-HHMMSS.json
```

Send `diagnostics-report.json` back for analysis.

The report intentionally contains controller serial numbers and device paths when Windows/SDL exposes them, because determining whether these values are stable is the purpose of the test. It does not intentionally collect username, hostname, unrelated files, or account data.

If the wizard fails before completion, it still attempts to save a partial report with `fatal_error` or `aborted_reason`.
