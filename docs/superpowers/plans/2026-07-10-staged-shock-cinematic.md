# Staged Shock Cinematic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the official competition shock tell a visible four-phase story on the Supply Map while preserving the existing deterministic backend response and trust guardrails.

**Architecture:** Add a pure presentation-phase model and a small React timer hook. `OverviewWorkspace` gates existing impact/recovery content by phase, while `MapView` consumes semantic phase classes and focuses the affected subnetwork. No API contract or exposure calculation changes.

**Tech Stack:** React 18, TypeScript, Vitest, React Leaflet/Leaflet, CSS animations, FastAPI demo API unchanged.

## Global Constraints

- Complete the sequence in at most 2.5 seconds: `origin` at 0 ms, `propagation` at 550 ms, `impact` at 1400 ms, `recovery` at 2200 ms.
- `simulateShock()` remains the only source of shock facts; no random or client-recomputed exposure values.
- Reset and unmount must cancel timers.
- `prefers-reduced-motion: reduce` resolves immediately to the final phase and disables decorative animation.
- Keep matching consent-gated and human-reviewed.
- Preserve advisory wording; do not imply automatic supplier replacement, credit approval, legal breach, or production readiness.
- Do not change backend contracts.

---

### Task 1: Pure Shock Presentation Model

**Files:**
- Create: `frontend/src/utils/shockPresentation.ts`
- Create: `frontend/src/utils/shockPresentation.test.ts`

**Interfaces:**
- Consumes: `ShockState` from `frontend/src/types.ts`.
- Produces: `ShockPresentationPhase`, `SHOCK_PHASE_SCHEDULE`, `phaseAtElapsedMs`, `isShockPhaseVisible`, `shockNodeVisualClass`, `shockEdgeVisualClass`, and `shockPhaseCopy`.

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, expect, it } from "vitest";
import type { ShockState } from "../types";
import {
  isShockPhaseVisible,
  phaseAtElapsedMs,
  shockEdgeVisualClass,
  shockNodeVisualClass,
  shockPhaseCopy
} from "./shockPresentation";

const shock: ShockState = {
  active: true,
  shockNodeId: "BIZ-005",
  affectedNodeIds: ["BIZ-009"],
  affectedEdgeIds: ["EDGE-1"],
  affectedSmeCount: 12,
  monthlyVolumeAtRisk: 199100,
  revenueAtRisk: 4800000000,
  avgStockoutDays: 0.9
};

describe("shock presentation", () => {
  it("advances through the four deterministic phases", () => {
    expect(phaseAtElapsedMs(false, 9999)).toBe("baseline");
    expect(phaseAtElapsedMs(true, 0)).toBe("origin");
    expect(phaseAtElapsedMs(true, 549)).toBe("origin");
    expect(phaseAtElapsedMs(true, 550)).toBe("propagation");
    expect(phaseAtElapsedMs(true, 1400)).toBe("impact");
    expect(phaseAtElapsedMs(true, 2200)).toBe("recovery");
    expect(phaseAtElapsedMs(true, 0, true)).toBe("recovery");
  });

  it("gates impact and recovery until their phases", () => {
    expect(isShockPhaseVisible("propagation", "impact")).toBe(false);
    expect(isShockPhaseVisible("impact", "impact")).toBe(true);
    expect(isShockPhaseVisible("impact", "recovery")).toBe(false);
    expect(isShockPhaseVisible("recovery", "recovery")).toBe(true);
  });

  it("assigns semantic map classes only when their phase is visible", () => {
    expect(shockNodeVisualClass("BIZ-005", shock, "origin")).toContain("shock-node-origin");
    expect(shockNodeVisualClass("BIZ-009", shock, "origin")).toBe("");
    expect(shockNodeVisualClass("BIZ-009", shock, "propagation")).toContain("shock-node-affected");
    expect(shockEdgeVisualClass("EDGE-1", 2, shock, "propagation")).toBe("shock-edge-impacted shock-edge-delay-2");
    expect(shockEdgeVisualClass("EDGE-2", 0, shock, "recovery")).toBe("");
  });

  it("turns returned facts into concise phase copy", () => {
    expect(shockPhaseCopy("origin", shock).metric).toContain("BIZ-005");
    expect(shockPhaseCopy("propagation", shock).metric).toContain("1 routes");
    expect(shockPhaseCopy("impact", shock).metric).toContain("12 SMEs");
    expect(shockPhaseCopy("recovery", shock).label).toBe("Recovery ready");
  });
});
```

- [ ] **Step 2: Run the test and verify RED**

Run: `cd frontend; npm.cmd exec vitest -- run src/utils/shockPresentation.test.ts --cache=false`

Expected: FAIL because `./shockPresentation` does not exist.

- [ ] **Step 3: Implement the pure model**

```ts
import type { ShockState } from "../types";

export type ShockPresentationPhase = "baseline" | "origin" | "propagation" | "impact" | "recovery";

export const SHOCK_PHASE_SCHEDULE: ReadonlyArray<{ phase: Exclude<ShockPresentationPhase, "baseline">; delayMs: number }> = [
  { phase: "origin", delayMs: 0 },
  { phase: "propagation", delayMs: 550 },
  { phase: "impact", delayMs: 1400 },
  { phase: "recovery", delayMs: 2200 }
];

const phaseRank: Record<ShockPresentationPhase, number> = {
  baseline: 0,
  origin: 1,
  propagation: 2,
  impact: 3,
  recovery: 4
};

export function phaseAtElapsedMs(active: boolean, elapsedMs: number, reducedMotion = false): ShockPresentationPhase {
  if (!active) return "baseline";
  if (reducedMotion) return "recovery";
  return [...SHOCK_PHASE_SCHEDULE].reverse().find((item) => elapsedMs >= item.delayMs)?.phase ?? "origin";
}

export function isShockPhaseVisible(current: ShockPresentationPhase, required: ShockPresentationPhase) {
  return phaseRank[current] >= phaseRank[required];
}

export function shockNodeVisualClass(nodeId: string, shock: ShockState, phase: ShockPresentationPhase) {
  if (!shock.active || phase === "baseline") return "";
  if (nodeId === shock.shockNodeId) return "shock-node-origin";
  if (isShockPhaseVisible(phase, "propagation") && shock.affectedNodeIds.includes(nodeId)) return "shock-node-affected";
  return "";
}

export function shockEdgeVisualClass(edgeId: string, index: number, shock: ShockState, phase: ShockPresentationPhase) {
  if (!shock.active || !isShockPhaseVisible(phase, "propagation") || !shock.affectedEdgeIds.includes(edgeId)) return "";
  return `shock-edge-impacted shock-edge-delay-${index % 4}`;
}

export function shockPhaseCopy(phase: ShockPresentationPhase, shock: ShockState) {
  if (phase === "origin") return { label: "Supplier disruption", metric: `${shock.shockNodeId} down` };
  if (phase === "propagation") return { label: "Impact propagating", metric: `${shock.affectedEdgeIds.length} routes exposed` };
  if (phase === "impact") return { label: "Operational exposure", metric: `${shock.affectedSmeCount} SMEs / ${shock.monthlyVolumeAtRisk.toLocaleString()} units` };
  if (phase === "recovery") return { label: "Recovery ready", metric: "Consent-gated shortlist" };
  return { label: "Network baseline", metric: "Monitoring live" };
}
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `cd frontend; npm.cmd exec vitest -- run src/utils/shockPresentation.test.ts --cache=false`

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/utils/shockPresentation.ts frontend/src/utils/shockPresentation.test.ts
git commit -m "Add shock presentation phase model"
```

### Task 2: Timer Hook And Overview Visibility Gates

**Files:**
- Create: `frontend/src/hooks/useShockPresentation.ts`
- Modify: `frontend/src/utils/shockSequence.ts`
- Modify: `frontend/src/utils/shockSequence.test.ts`
- Modify: `frontend/src/components/WorkspaceViews.tsx`

**Interfaces:**
- Consumes: `SHOCK_PHASE_SCHEDULE` and `ShockPresentationPhase` from Task 1.
- Produces: `useShockPresentation(active: boolean): ShockPresentationPhase`; `shockSequenceSteps` accepts optional `presentationPhase`.

- [ ] **Step 1: Add a failing sequence-gating test**

```ts
it("keeps recovery blocked until the cinematic recovery phase", () => {
  const propagating = shockSequenceSteps({
    shock: { ...baseShock, active: true },
    canOpenMatching: true,
    shockTargetName: "Dai Tin Distribution",
    presentationPhase: "propagation"
  });
  const recovered = shockSequenceSteps({
    shock: { ...baseShock, active: true },
    canOpenMatching: true,
    shockTargetName: "Dai Tin Distribution",
    presentationPhase: "recovery"
  });
  expect(propagating.find((step) => step.id === "recovery")?.status).toBe("blocked");
  expect(recovered.find((step) => step.id === "recovery")?.status).toBe("ready");
});
```

- [ ] **Step 2: Run the test and verify RED**

Run: `cd frontend; npm.cmd exec vitest -- run src/utils/shockSequence.test.ts --cache=false`

Expected: TypeScript/test failure because `presentationPhase` is not accepted and recovery is immediately ready.

- [ ] **Step 3: Implement the timer hook**

```ts
import { useEffect, useState } from "react";
import { SHOCK_PHASE_SCHEDULE, type ShockPresentationPhase } from "../utils/shockPresentation";

export function useShockPresentation(active: boolean): ShockPresentationPhase {
  const [phase, setPhase] = useState<ShockPresentationPhase>("baseline");

  useEffect(() => {
    if (!active) {
      setPhase("baseline");
      return;
    }
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    if (reducedMotion) {
      setPhase("recovery");
      return;
    }
    setPhase("origin");
    const timers = SHOCK_PHASE_SCHEDULE.slice(1).map(({ phase: nextPhase, delayMs }) =>
      window.setTimeout(() => setPhase(nextPhase), delayMs)
    );
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [active]);

  return phase;
}
```

- [ ] **Step 4: Gate the sequence and Overview content**

In `shockSequenceSteps`, accept `presentationPhase?: ShockPresentationPhase`, default active shocks to `"recovery"` for backwards compatibility, and return recovery status `blocked` until `isShockPhaseVisible(phase, "recovery")`.

In `OverviewWorkspace`:

```tsx
const presentationPhase = useShockPresentation(shock.active);
const showImpact = isShockPhaseVisible(presentationPhase, "impact");
const showRecovery = isShockPhaseVisible(presentationPhase, "recovery");
const shockSequence = shockSequenceSteps({ shock, canOpenMatching, shockTargetName, presentationPhase });
```

Pass `presentationPhase` to `MapView`; render `.map-shock-banner` and `.shock-impact-panel` only when `showImpact`; render the recovery playbook and recovery CTA only when `showRecovery`; add `data-testid="shock-presentation"` and `data-phase={presentationPhase}` to the overview root.

- [ ] **Step 5: Run focused tests and build**

Run: `cd frontend; npm.cmd exec vitest -- run src/utils/shockPresentation.test.ts src/utils/shockSequence.test.ts --cache=false`

Expected: PASS, 10 tests after the new sequence test.

Run: `cd frontend; npm.cmd run build`

Expected: TypeScript and Vite build exit 0.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/hooks/useShockPresentation.ts frontend/src/utils/shockSequence.ts frontend/src/utils/shockSequence.test.ts frontend/src/components/WorkspaceViews.tsx
git commit -m "Stage shock impact and recovery UI"
```

### Task 3: Map Focus And Propagation Styling

**Files:**
- Modify: `frontend/src/components/MapView.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/utils/shockPresentation.test.ts`

**Interfaces:**
- Consumes: `ShockPresentationPhase`, `isShockPhaseVisible`, `shockNodeVisualClass`, `shockEdgeVisualClass`, `shockPhaseCopy`.
- Produces: stable DOM hooks `data-testid="southern-map"`, `data-shock-phase`, `.shock-node-origin`, `.shock-node-affected`, `.shock-edge-impacted`, and `.map-phase-overlay`.

- [ ] **Step 1: Extend the failing class tests**

Add assertions that baseline never emits map classes, a non-affected edge never emits a class, and delay classes wrap from index 4 to delay 0.

```ts
expect(shockNodeVisualClass("BIZ-005", shock, "baseline")).toBe("");
expect(shockEdgeVisualClass("EDGE-2", 0, shock, "propagation")).toBe("");
expect(shockEdgeVisualClass("EDGE-1", 4, shock, "propagation")).toBe("shock-edge-impacted shock-edge-delay-0");
```

- [ ] **Step 2: Run the focused test and verify behavior**

Run: `cd frontend; npm.cmd exec vitest -- run src/utils/shockPresentation.test.ts --cache=false`

Expected: PASS if Task 1 already covers modulo behavior; if it passes immediately, retain it as explicit regression coverage and do not change production behavior for this step.

- [ ] **Step 3: Add phase-aware map rendering**

Change `MapViewProps` to include `presentationPhase: ShockPresentationPhase`. Update `FitNetwork` so an active non-baseline phase fits the disrupted node plus affected nodes with `{ padding: [70, 70], maxZoom: 10 }`; otherwise preserve existing network bounds.

For impacted polylines:

```tsx
const visualClass = shockEdgeVisualClass(edge.id, index, shock, presentationPhase);
const pathOptions: PathOptions = {
  className: visualClass,
  color: visualClass ? "#fb7185" : support ? "#c084fc" : "#22d3ee",
  weight: visualClass ? 4 : support ? 1.8 : 1.25,
  opacity: visualClass ? 1 : support ? 0.72 : 0.46,
  dashArray: visualClass ? "7 7" : support ? "3 5" : undefined
};
```

For each node, pass `className: shockNodeVisualClass(node.id, shock, presentationPhase)` in `pathOptions`. Render one non-interactive outer `CircleMarker` with class `shock-origin-halo` around the disrupted supplier for all non-baseline phases.

Add the phase overlay:

```tsx
const phaseCopy = shockPhaseCopy(presentationPhase, shock);
<div className={`map-phase-overlay ${presentationPhase}`} data-testid="map-phase-overlay">
  <span>{phaseCopy.label}</span>
  <strong>{phaseCopy.metric}</strong>
</div>
```

- [ ] **Step 4: Add restrained cinematic CSS**

```css
.map-phase-overlay { position: absolute; top: 12px; right: 12px; z-index: 500; min-width: 180px; padding: 9px 11px; border: 1px solid rgba(251, 113, 133, 0.4); border-radius: 6px; background: rgba(5, 11, 16, 0.9); pointer-events: none; }
.map-phase-overlay span, .map-phase-overlay strong { display: block; }
.map-phase-overlay span { color: var(--muted); font-size: 9px; text-transform: uppercase; }
.map-phase-overlay strong { margin-top: 3px; color: #ffe4e6; font-size: 12px; }
.leaflet-interactive.shock-origin-halo { animation: shock-origin-pulse 900ms ease-out infinite; }
.leaflet-interactive.shock-node-origin { filter: drop-shadow(0 0 8px rgba(251, 91, 89, 0.95)); }
.leaflet-interactive.shock-node-affected { animation: shock-node-pulse 850ms ease-in-out 2; filter: drop-shadow(0 0 6px rgba(245, 158, 11, 0.88)); }
.leaflet-interactive.shock-edge-impacted { animation: shock-route-reveal 720ms ease-out both, shock-route-flow 900ms linear infinite 720ms; }
.shock-edge-delay-1 { animation-delay: 120ms, 840ms; }
.shock-edge-delay-2 { animation-delay: 240ms, 960ms; }
.shock-edge-delay-3 { animation-delay: 360ms, 1080ms; }
@keyframes shock-origin-pulse { 0% { stroke-opacity: 0.9; stroke-width: 2; } 100% { stroke-opacity: 0; stroke-width: 16; } }
@keyframes shock-node-pulse { 50% { fill-opacity: 0.45; stroke-width: 6; } }
@keyframes shock-route-reveal { from { stroke-dashoffset: 40; stroke-opacity: 0; } to { stroke-dashoffset: 0; stroke-opacity: 1; } }
@keyframes shock-route-flow { to { stroke-dashoffset: -28; } }
@media (prefers-reduced-motion: reduce) { .leaflet-interactive.shock-origin-halo, .leaflet-interactive.shock-node-affected, .leaflet-interactive.shock-edge-impacted { animation: none; } }
```

On screens below 600 px, place `.map-phase-overlay` below the existing left overlay and cap its width with `max-width: calc(100% - 24px)`.

- [ ] **Step 5: Run tests, build, and bundle gate**

Run: `cd frontend; npm.cmd test -- --run --cache=false`

Expected: all frontend tests pass.

Run: `cd frontend; npm.cmd run build`

Expected: build exits 0 with no chunk-size warning.

Run: `cd frontend; npm.cmd run test:bundle`

Expected: largest JS chunk remains under the repository budget.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/components/MapView.tsx frontend/src/styles.css frontend/src/utils/shockPresentation.test.ts
git commit -m "Animate staged shock propagation on map"
```

### Task 4: Official Demo Verification And Handoff

**Files:**
- Modify: `docs/21-competition-demo-runbook.md`
- Modify: `PROJECT_STATE.md`

**Interfaces:**
- Consumes: official URL and account from `docs/21-competition-demo-runbook.md`.
- Produces: current verification evidence and next-work handoff.

- [ ] **Step 1: Update the runbook**

In the Shock step, instruct the presenter to let the 2.2-second sequence finish before reading impact, and name the four visual phases. Keep the existing “decision support” language.

- [ ] **Step 2: Run complete verification**

Run: `cd frontend; npm.cmd test -- --run --cache=false`

Run: `cd frontend; npm.cmd run build`

Run: `cd frontend; npm.cmd run test:bundle`

Run: `python -B -m unittest discover -s backend\tests`

Expected: all frontend/backend tests pass; build and bundle gates exit 0.

- [ ] **Step 3: Verify the official browser route**

Open `http://127.0.0.1:5173/?view=overview&account=demo-operator&business=BIZ-005&period=2026-07` and verify:

- Phase starts at `origin`, then reaches `propagation`, `impact`, and `recovery` in order.
- Impact banner/panel is absent before `impact`.
- Recovery playbook/CTA is absent before `recovery`.
- At least one `.shock-edge-impacted`, one `.shock-node-origin`, and one `.shock-node-affected` exist after propagation.
- Reset leaves `data-phase="baseline"` after 2.5 seconds.
- Desktop 1280x720 and mobile 390x844 have no horizontal overflow or console errors.

- [ ] **Step 4: Update project state with exact evidence**

Record test counts, build chunk size, browser phase sequence, desktop/mobile overflow result, and the remaining next-best work. Do not claim production readiness.

- [ ] **Step 5: Verify diff and commit**

Run: `git diff --check`

Expected: no output, exit 0.

```powershell
git add docs/21-competition-demo-runbook.md PROJECT_STATE.md
git commit -m "Document staged shock demo flow"
```

- [ ] **Step 6: Rebase and push**

Run: `git pull --rebase origin main`

Run: `git push origin main`

Expected: `main` and `origin/main` point to the same final commit.
