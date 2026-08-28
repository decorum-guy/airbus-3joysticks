# FCU validation matrix

Hardware/simulator validation is authoritative. Generic SimConnect events must not be treated as validated merely because they exist in the SDK.

## Tested aircraft

- SimConnect TITLE: `A320neo Global Livery`
- ATC model observed in the guided diagnostic: `A20N`
- Validation date: 2026-08-28

## Current results

| FCU control | Candidate event(s) | Result | Notes |
| --- | --- | --- | --- |
| SPD rotary | `AP_SPD_VAR_INC` / `AP_SPD_VAR_DEC` | **REJECTED / unsafe for production** | Focused probe started with SimVar 140 kt. The first INC changed it to 101 kt; five INC events ended at 105 kt, matching the user's visible FCU report. Five DEC events then ended at 100 kt rather than restoring 140 kt. Do not bind the production SPD rotary to these generic events. Use a verified A320-specific InputEvent/RPN/MobiFlight path instead. |
| HDG rotary | `HEADING_BUG_INC` / `HEADING_BUG_DEC` | **Validated** | 70→71→72→73→74→75, visible FCU reported 75, then clean restore 75→70. |
| ALT rotary | `AP_ALT_VAR_INC` / `AP_ALT_VAR_DEC` | **Validated** | 20000→21000→22000 ft, visible FCU reported 22000, then clean restore to 20000. |
| V/S clockwise | `AP_VS_VAR_INC` | **Validated for increment** | Focused probe: +1000→+1100→+1200→+1300→+1400→+1500 fpm, visible FCU reported 1500. |
| V/S counter-clockwise | `AP_VS_VAR_DEC` | **Needs focused verification** | The original broad probe produced ambiguous state-dependent behavior. Run a dedicated decrement probe before treating counter-clockwise V/S as production-safe. |

## Safety rule

A rejected or unverified FCU action must remain `pending` in the production controller profile. Diagnostic scripts may still send it when the user explicitly consents to a focused test.
