# FCU validation matrix

Hardware/simulator validation is authoritative. Generic SimConnect events must not be treated as validated merely because they exist in the SDK.

## Tested aircraft

- SimConnect TITLE: `A320neo Global Livery`
- ATC model observed in the guided diagnostic: `A20N`
- Validation date: 2026-08-28

## Current results

| FCU control | Candidate event(s) | Result | Notes |
| --- | --- | --- | --- |
| SPD rotary | `AP_SPD_VAR_INC` / `AP_SPD_VAR_DEC` | **Validated** | The original active probe cleanly produced 140→141→140. A later focused probe appeared to show 140→101, but the user clarified that they manually changed the FCU speed to 100 after the probe's initial 140 snapshot and before the scripted increment sequence. From the actual cockpit baseline of 100, the script then correctly produced 101→102→103→104→105 and restored 105→100. The apparent jump was therefore a stale pre-probe snapshot caused by manual interaction, not an event failure. |
| HDG rotary | `HEADING_BUG_INC` / `HEADING_BUG_DEC` | **Validated** | 70→71→72→73→74→75, visible FCU reported 75, then clean restore 75→70. |
| ALT rotary | `AP_ALT_VAR_INC` / `AP_ALT_VAR_DEC` | **Validated** | 20000→21000→22000 ft, visible FCU reported 22000, then clean restore to 20000. |
| V/S clockwise | `AP_VS_VAR_INC` | **Validated** | Focused probe: +1000→+1100→+1200→+1300→+1400→+1500 fpm, visible FCU reported 1500. |
| V/S counter-clockwise | `AP_VS_VAR_DEC` | **Validated** | End-to-end production-runtime test on 2026-08-28: rotating the RIGHT controller's V/S stick counter-clockwise repeatedly drove the visible FCU V/S target downward through zero into negative values, and clockwise rotation returned it upward normally. |

## Rotary core status

All four active FCU rotary controls are now validated in both directions on the tested A320neo setup:

- SPEED
- HEADING
- ALTITUDE
- V/S

The remaining rotary work is interaction tuning (precision/acceleration), not SimConnect event validation.

## Safety rule

A rejected or unverified FCU action must remain `pending` in the production controller profile. Diagnostic scripts may still send it when the user explicitly consents to a focused test.
