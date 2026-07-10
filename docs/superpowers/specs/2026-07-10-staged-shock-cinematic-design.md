# Staged Shock Cinematic Design

## Context

The competition story already computes a deterministic supplier shock and a guarded recovery playbook. The current map applies every visual change at once, so judges must infer propagation from small route styling and KPI changes.

## Goal

Turn the existing shock into a clear 2-3 second presentation sequence without changing backend facts, authorization, consent, or recovery logic.

Success means a viewer can understand this chain without narration:

`supplier down -> routes propagate impact -> SMEs and volume exposed -> recovery ready`

## Approaches Considered

1. **Frontend presentation state machine (selected).** Keep one backend response and reveal its existing facts in four deterministic visual phases. Strong story, low API risk, testable with pure state helpers.
2. **Static impact emphasis.** Improve contrast and labels without timing. Lower motion risk but does not create a competition-demo climax.
3. **Backend streaming simulation.** Stream propagation events from FastAPI. More realistic, but adds protocol, reconnect, and ordering complexity without improving the underlying deterministic demo evidence.

## Interaction Design

- Baseline: map shows current network and the existing Run command.
- Phase 1, `origin` (0-550 ms): the disrupted supplier gains a visible failure pulse and the map focuses on the affected subnetwork.
- Phase 2, `propagation` (550-1400 ms): impacted routes illuminate with staggered delays; exposed nodes gain an amber pulse.
- Phase 3, `impact` (1400-2200 ms): the map overlay and impact KPIs reveal SMEs, volume, revenue, and stockout window.
- Phase 4, `recovery` (after 2200 ms): the recovery CTA and existing playbook become available.
- Reset immediately restores baseline and cancels pending transitions.
- Running another view or unmounting the workspace cancels timers.
- With `prefers-reduced-motion: reduce`, phases advance immediately and animations are disabled.

## Components

### `shockPresentation.ts`

A pure helper defines phase order, delays, labels, and which facts are visible. It has no React, map, or API dependency.

### `useShockPresentation`

A focused hook owns transition timers. It receives `shock.active`, returns the current phase, and cleans up on reset/unmount. It never mutates shock data.

### `MapView`

- Receives the presentation phase.
- Adds semantic CSS classes to disrupted node, affected nodes, and affected routes.
- Fits bounds to the disrupted plus affected nodes when Phase 1 starts.
- Shows a compact map overlay for the active phase.
- Keeps map controls and node selection usable after the sequence.

### `OverviewWorkspace`

- Uses phase visibility to reveal impact and recovery sections.
- Keeps the existing shock sequence, recovery playbook, and guardrail copy.
- Exposes stable `data-testid` values for phase and map-state verification.

## Data And Trust Boundaries

- `simulateShock()` remains the only source of shock facts.
- No random values or client-side recomputation of exposure are introduced.
- Matching remains consent-gated and human-reviewed.
- Existing wording remains advisory and never implies automatic supplier replacement, credit approval, or a legal conclusion.

## Error Handling

- If shock simulation fails, presentation remains at baseline and existing API error behavior applies.
- Empty affected-node or affected-edge arrays still show the origin phase, then the returned impact values.
- Missing map nodes are ignored when fitting bounds; the current viewport remains if no valid coordinates exist.

## Testing

- Pure unit tests prove phase order, timing, reset behavior, and visibility gates.
- Hook/component tests prove timers are cleaned up and reduced-motion resolves immediately where practical.
- Existing frontend tests, TypeScript build, and bundle budget must remain green.
- Browser verification proves the official URL reaches all four phases, affected routes/nodes receive classes, recovery is hidden before its phase, and desktop/mobile have no horizontal overflow or console errors.

## Acceptance Criteria

- One click produces the four ordered phases in at most 2.5 seconds.
- The disrupted supplier and propagated routes are visually distinguishable at desktop and mobile sizes.
- Impact values do not appear before the impact phase; recovery does not appear before the recovery phase.
- Reset returns to baseline without delayed UI reappearing.
- Reduced-motion users receive the final state without decorative motion.
- No backend contract or legal/product guardrail changes.

## Out Of Scope

- Real-time event streaming, stochastic simulation, user-adjustable shock parameters, new risk formulas, map redesign, or production-readiness claims.
