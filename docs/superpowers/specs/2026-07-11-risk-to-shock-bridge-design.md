# Risk-to-Shock Bridge Design

## Context

The competition flow explains an evidence-backed risk signal and then demonstrates a network shock. The current Risk workspace jumps directly to Matching, so the causal story skips the operational consequence between an observed signal and a recovery shortlist.

## Decision

Add a compact Operational Scenario bridge inside the Risk workspace. It reuses the existing `RiskSignal`, `ShockState`, and shock simulation endpoint. The endpoint is hardened in place with a dedicated execution capability, selected-period context, policy/audit correlation, and deterministic run provenance; no new endpoint, score, forecast, or persisted analytics table is added.

The bridge separates two concepts:

- Observed signal: deterministic rules and policy-scoped evidence already returned by the risk API.
- Hypothetical disruption: a user-triggered network scenario that traces downstream operational exposure.

## User Flow

1. The presenter opens `BIZ-005` in Risk Analysis for the selected month.
2. The bridge shows a ready state without exposing stale or fallback impact values.
3. The presenter clicks `Run operational scenario`.
4. The existing shock simulation runs, then the app opens Overview with the staged map cinematic.
5. If a provenance-complete result matches the selected period, the bridge shows the calculated impact and the CTA becomes `View scenario results`.
6. For a risk subject that does not match the supported shock node, the bridge remains visible but disabled and explains that no scoped scenario is available.
7. `Review alternatives` remains an independent human-review path; running a shock is not an artificial prerequisite for Matching.

## Component Boundaries

### `riskShockBridge.ts`

- Converts `RiskSignal`, `ShockState`, subject name, selected period, and policy capability into a display model.
- Returns `ready`, `result`, or `unavailable` state.
- Hides exact impact values in `ready` state so fallback seed values cannot be mistaken for calculated output.
- Rejects stale-period and incomplete-provenance results; synthetic fallback is labeled explicitly.
- Emits the legal/product guardrail copy from one testable source.

### `RiskWorkspace`

- Renders the bridge directly after the risk summary band.
- Shows the selected period and the distinction between observed evidence and a hypothetical scenario.
- Uses a single icon-and-text CTA with a stable `data-testid` and `data-state` for browser QA.
- Keeps the existing `Review alternatives` action available while making the scenario the highlighted competition-story handoff.

### `App`

- Supplies the current `ShockState`, selected period, graph-read capability, and separate shock-execution capability.
- Runs the existing simulation for a ready bridge, validates result context, and opens Overview without waiting on Matching data.
- Opens Overview without rerunning when the scenario is already active.
- Scopes Overview, Map, Matching, and recovery-data loading to a result matching the selected period.

## Copy And Guardrails

- Never call the bridge a forecast, probability, breach finding, or automated supplier decision.
- Ready-state metrics use action labels such as `Trace`, `Calculate`, and `Estimate`, not seeded numbers.
- Result-state metrics use only the returned shock result.
- Required notice: `Hypothetical decision-support scenario. Not a forecast, legal finding, or supplier replacement instruction.`
- Every non-fallback result exposes period, run, ruleset, model, policy decision, audit event, and result source.

## Error And Access Behavior

- Existing shock API errors retain the explicit synthetic demo fallback boundary; non-demo failures are caught and do not apply a result.
- The bridge action is disabled independently for graph denial, execution denial, or an unsupported risk subject.
- Overview Run controls use the same capability and show the policy boundary instead of silently doing nothing.
- Recommendation loading is failure-isolated from scenario execution.
- The Risk locked state remains unchanged and never renders scenario details.

## Verification

- Pure unit tests cover ready, result, stale-period, missing-provenance, fallback, mismatched-subject, and split capability states plus guardrail wording.
- Existing frontend tests, TypeScript build, and bundle budget must remain green.
- Browser QA follows the official URL and verifies Risk -> scenario -> Overview phase progression on desktop and mobile, with no horizontal overflow or console errors.
