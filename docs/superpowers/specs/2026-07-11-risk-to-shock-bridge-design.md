# Risk-to-Shock Bridge Design

## Context

The competition flow explains an evidence-backed risk signal and then demonstrates a network shock. The current Risk workspace jumps directly to Matching, so the causal story skips the operational consequence between an observed signal and a recovery shortlist.

## Decision

Add a compact Operational Scenario bridge inside the Risk workspace. It reuses the existing `RiskSignal`, `ShockState`, and shock simulation endpoint. No backend endpoint, score, forecast, or persisted analytics record is added in this slice.

The bridge separates two concepts:

- Observed signal: deterministic rules and policy-scoped evidence already returned by the risk API.
- Hypothetical disruption: a user-triggered network scenario that traces downstream operational exposure.

## User Flow

1. The presenter opens `BIZ-005` in Risk Analysis for the selected month.
2. The bridge shows a ready state without exposing stale or fallback impact values.
3. The presenter clicks `Run operational scenario`.
4. The existing shock simulation runs, then the app opens Overview with the staged map cinematic.
5. If the scenario is already active, the bridge shows the calculated impact and the CTA becomes `View live scenario`.
6. For a risk subject that does not match the supported shock node, the bridge remains visible but disabled and explains that no scoped scenario is available.
7. `Review alternatives` remains an independent human-review path; running a shock is not an artificial prerequisite for Matching.

## Component Boundaries

### `riskShockBridge.ts`

- Converts `RiskSignal`, `ShockState`, subject name, selected period, and policy capability into a display model.
- Returns `ready`, `live`, or `unavailable` state.
- Hides exact impact values in `ready` state so fallback seed values cannot be mistaken for calculated output.
- Emits the legal/product guardrail copy from one testable source.

### `RiskWorkspace`

- Renders the bridge directly after the risk summary band.
- Shows the selected period and the distinction between observed evidence and a hypothetical scenario.
- Uses a single icon-and-text CTA with a stable `data-testid` and `data-state` for browser QA.
- Keeps the existing `Review alternatives` action available while making the scenario the highlighted competition-story handoff.

### `App`

- Supplies the current `ShockState`, selected period, and graph capability.
- Runs the existing simulation for a ready bridge and opens Overview after a successful result.
- Opens Overview without rerunning when the scenario is already active.

## Copy And Guardrails

- Never call the bridge a forecast, probability, breach finding, or automated supplier decision.
- Ready-state metrics use action labels such as `Trace`, `Calculate`, and `Estimate`, not seeded numbers.
- Live-state metrics use only the returned shock result.
- Required notice: `Hypothetical decision-support scenario. Not a forecast, legal finding, or supplier replacement instruction.`
- Existing policy decision, audit ID, evidence scope, consent, and human-review controls remain unchanged.

## Error And Access Behavior

- Existing shock API errors retain the current demo fallback boundary; non-demo errors are not silently converted.
- The bridge action is disabled when graph access is unavailable or the selected risk subject is not the supported shock node.
- The Risk locked state remains unchanged and never renders scenario details.

## Verification

- Pure unit tests cover ready, live, mismatched-subject, and capability-denied states plus guardrail wording.
- Existing frontend tests, TypeScript build, and bundle budget must remain green.
- Browser QA follows the official URL and verifies Risk -> scenario -> Overview phase progression on desktop and mobile, with no horizontal overflow or console errors.
