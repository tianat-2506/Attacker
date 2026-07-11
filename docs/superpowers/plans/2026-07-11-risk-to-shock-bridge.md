# Risk-to-Shock Bridge Implementation Plan

> **Status:** Implemented with QA corrections. The detailed steps below preserve the original TDD sequence; this revision governs wherever they conflict.

## QA Revision

- Final states are `ready`, `result`, and `unavailable`; avoid “live” claims.
- The existing shock endpoint now accepts `period_key`, requires `simulate_shock`, and returns run/ruleset/model/source plus policy and audit provenance.
- Graph read and shock execution are separate capabilities; denied execution is audited.
- A displayed result must match the selected period and have complete provenance. Demo fallback is explicitly synthetic.
- Shock execution is independent from recommendation loading; Overview/Map/Matching ignore stale-period results.
- Overview Run controls are capability-aware, and Matching remains independently accessible for human review.
- Final verification counts and runtime evidence are maintained in `PROJECT_STATE.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the evidence-backed Risk workspace to the staged Shock cinematic with a compact, policy-safe operational scenario handoff.

**Architecture:** A pure utility converts risk/shock/access inputs into a `ready`, `result`, or `unavailable` display model. A focused React component renders that model. `App` owns policy-aware simulation, period scoping and route transition, while `RiskWorkspace` remains responsible for page composition.

**Tech Stack:** React 18, TypeScript 5.6, Vitest 2, React DOM server rendering, existing CSS and lucide-react icons.

## Global Constraints

- Do not add a new endpoint; harden the existing endpoint contract as described in the QA revision.
- Do not show seeded impact numbers before the shock endpoint returns a live result.
- Use only returned `ShockState` values in the live bridge.
- Keep `Review alternatives` independent from running a shock.
- Preserve policy, consent, period, audit, and human-review boundaries.
- Render this exact notice: `Hypothetical decision-support scenario. Not a forecast, legal finding, or supplier replacement instruction.`

---

### Task 1: Pure Risk-to-Shock View Model

**Files:**
- Create: `frontend/src/utils/riskShockBridge.ts`
- Create: `frontend/src/utils/riskShockBridge.test.ts`

**Interfaces:**
- Consumes: `ShockState`, risk subject ID, subject name, monthly period key, and graph capability.
- Produces: `riskShockBridgeModel(input): RiskShockBridgeModel` with `state`, copy, metrics, action, label, disabled state, and guardrail.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from "vitest";
import type { ShockState } from "../types";
import { riskShockBridgeModel } from "./riskShockBridge";

const shock: ShockState = {
  active: false,
  shockNodeId: "BIZ-005",
  affectedNodeIds: ["BIZ-009"],
  affectedEdgeIds: ["EDGE-055", "EDGE-056"],
  affectedSmeCount: 12,
  monthlyVolumeAtRisk: 199060,
  revenueAtRisk: 4800000000,
  avgStockoutDays: 3.8
};

function model(overrides: Partial<Parameters<typeof riskShockBridgeModel>[0]> = {}) {
  return riskShockBridgeModel({
    signalBusinessId: "BIZ-005",
    subjectName: "Dai Tin Distribution",
    periodKey: "2026-07",
    canRunScenario: true,
    shock,
    ...overrides
  });
}

describe("riskShockBridgeModel", () => {
  it("keeps seeded impact values hidden before a scenario runs", () => {
    const bridge = model();
    expect(bridge.state).toBe("ready");
    expect(bridge.action).toBe("run");
    expect(bridge.metrics.map((metric) => metric.value)).toEqual(["Trace", "Map", "Calculate", "Estimate"]);
    expect(JSON.stringify(bridge)).not.toContain("199");
  });

  it("shows only returned impact values for a live matching scenario", () => {
    const bridge = model({ shock: { ...shock, active: true } });
    expect(bridge.state).toBe("live");
    expect(bridge.action).toBe("open");
    expect(bridge.metrics.map((metric) => metric.value)).toEqual(["2", "12", "199.1K units/mo", "3.8 days"]);
  });

  it("blocks mismatched subjects and denied graph access", () => {
    expect(model({ signalBusinessId: "BIZ-013" }).action).toBe("none");
    expect(model({ canRunScenario: false }).disabled).toBe(true);
  });

  it("keeps the scenario wording inside product and legal boundaries", () => {
    const bridge = model();
    expect(bridge.guardrail).toBe("Hypothetical decision-support scenario. Not a forecast, legal finding, or supplier replacement instruction.");
    expect(`${bridge.headline} ${bridge.detail}`.toLowerCase()).not.toContain("probability");
  });
});
```

- [ ] **Step 2: Run the test to verify RED**

Run: `cd frontend; npm.cmd exec vitest -- run src/utils/riskShockBridge.test.ts --cache=false`

Expected: FAIL because `./riskShockBridge` does not exist.

- [ ] **Step 3: Implement the minimal view model**

```ts
import type { ShockState } from "../types";

export type RiskShockBridgeState = "ready" | "live" | "unavailable";
export type RiskShockBridgeAction = "run" | "open" | "none";

export interface RiskShockBridgeMetric {
  label: string;
  value: string;
}

export interface RiskShockBridgeModel {
  state: RiskShockBridgeState;
  eyebrow: string;
  headline: string;
  detail: string;
  metrics: RiskShockBridgeMetric[];
  action: RiskShockBridgeAction;
  actionLabel: string;
  disabled: boolean;
  guardrail: string;
}

const compactNumber = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const guardrail = "Hypothetical decision-support scenario. Not a forecast, legal finding, or supplier replacement instruction.";

export function riskShockBridgeModel({
  signalBusinessId,
  subjectName,
  periodKey,
  canRunScenario,
  shock
}: {
  signalBusinessId: string;
  subjectName: string;
  periodKey: string;
  canRunScenario: boolean;
  shock: ShockState;
}): RiskShockBridgeModel {
  if (!canRunScenario || signalBusinessId !== shock.shockNodeId) {
    return {
      state: "unavailable",
      eyebrow: "Scenario access boundary",
      headline: "No scoped operational scenario for this signal",
      detail: "The selected account or risk subject does not have an available graph scenario for this period.",
      metrics: [],
      action: "none",
      actionLabel: "Scenario unavailable",
      disabled: true,
      guardrail
    };
  }

  if (!shock.active) {
    return {
      state: "ready",
      eyebrow: "Observed signal to hypothetical scenario",
      headline: "Test the network consequence of this signal",
      detail: `Run a hypothetical disruption at ${subjectName} for ${periodKey}. The model traces visible network relationships and calculates operational exposure.`,
      metrics: [
        { label: "Affected routes", value: "Trace" },
        { label: "Downstream SMEs", value: "Map" },
        { label: "Exposed volume", value: "Calculate" },
        { label: "Stockout window", value: "Estimate" }
      ],
      action: "run",
      actionLabel: "Run operational scenario",
      disabled: false,
      guardrail
    };
  }

  return {
    state: "live",
    eyebrow: "Operational scenario calculated",
    headline: `Exposure traced from ${subjectName}`,
    detail: `The ${periodKey} scenario follows visible downstream routes from the selected disruption point.`,
    metrics: [
      { label: "Affected routes", value: String(shock.affectedEdgeIds.length) },
      { label: "Downstream SMEs", value: String(shock.affectedSmeCount) },
      { label: "Exposed volume", value: `${compactNumber.format(shock.monthlyVolumeAtRisk)} units/mo` },
      { label: "Stockout window", value: `${shock.avgStockoutDays.toFixed(1)} days` }
    ],
    action: "open",
    actionLabel: "View live scenario",
    disabled: false,
    guardrail
  };
}
```

- [ ] **Step 4: Run the focused test to verify GREEN**

Run: `cd frontend; npm.cmd exec vitest -- run src/utils/riskShockBridge.test.ts --cache=false`

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/riskShockBridge.ts frontend/src/utils/riskShockBridge.test.ts
git commit -m "Add risk-to-shock bridge model"
```

---

### Task 2: Render And Wire The Operational Scenario Handoff

**Files:**
- Create: `frontend/src/components/RiskShockBridge.tsx`
- Create: `frontend/src/components/RiskShockBridge.test.tsx`
- Modify: `frontend/src/components/WorkspaceViews.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `RiskShockBridgeModel`, `onOpenScenario(): void`.
- Produces: a stable `risk-shock-bridge` DOM contract and Risk -> Overview simulation handoff.

- [ ] **Step 1: Write the failing render test**

```tsx
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { RiskShockBridgeModel } from "../utils/riskShockBridge";
import { RiskShockBridge } from "./RiskShockBridge";

const ready: RiskShockBridgeModel = {
  state: "ready",
  eyebrow: "Observed signal to hypothetical scenario",
  headline: "Test the network consequence of this signal",
  detail: "Run the selected scenario.",
  metrics: [{ label: "Affected routes", value: "Trace" }],
  action: "run",
  actionLabel: "Run operational scenario",
  disabled: false,
  guardrail: "Hypothetical decision-support scenario. Not a forecast, legal finding, or supplier replacement instruction."
};

describe("RiskShockBridge", () => {
  it("renders a stable ready-state handoff without inventing a result", () => {
    const html = renderToStaticMarkup(<RiskShockBridge model={ready} onOpenScenario={vi.fn()} />);
    expect(html).toContain('data-testid="risk-shock-bridge"');
    expect(html).toContain('data-state="ready"');
    expect(html).toContain("Run operational scenario");
    expect(html).toContain("Not a forecast");
  });

  it("disables an unavailable scenario action", () => {
    const html = renderToStaticMarkup(<RiskShockBridge model={{ ...ready, state: "unavailable", action: "none", actionLabel: "Scenario unavailable", disabled: true }} onOpenScenario={vi.fn()} />);
    expect(html).toContain("disabled");
  });
});
```

- [ ] **Step 2: Run the render test to verify RED**

Run: `cd frontend; npm.cmd exec vitest -- run src/components/RiskShockBridge.test.tsx --cache=false`

Expected: FAIL because `./RiskShockBridge` does not exist.

- [ ] **Step 3: Add the focused presentational component**

```tsx
import { ArrowRight, GitBranch, Route, ShieldCheck } from "lucide-react";
import type { RiskShockBridgeModel } from "../utils/riskShockBridge";

export function RiskShockBridge({ model, onOpenScenario }: { model: RiskShockBridgeModel; onOpenScenario: () => void }) {
  return (
    <section className={`risk-shock-bridge ${model.state}`} data-testid="risk-shock-bridge" data-state={model.state}>
      <div className="risk-shock-flow" aria-label="Risk to operational scenario">
        <span><ShieldCheck size={17} /><small>Observed</small><strong>Risk signal</strong></span>
        <ArrowRight size={16} />
        <span><GitBranch size={17} /><small>Hypothetical</small><strong>Network shock</strong></span>
      </div>
      <div className="risk-shock-copy">
        <span className="eyebrow">{model.eyebrow}</span>
        <h2>{model.headline}</h2>
        <p>{model.detail}</p>
        <small>{model.guardrail}</small>
      </div>
      <div className="risk-shock-metrics">
        {model.metrics.map((metric) => <span key={metric.label}><strong>{metric.value}</strong><small>{metric.label}</small></span>)}
      </div>
      <button className="primary-button" type="button" disabled={model.disabled} onClick={onOpenScenario}>
        <Route size={16} />{model.actionLabel}<ArrowRight size={15} />
      </button>
    </section>
  );
}
```

- [ ] **Step 4: Wire the model into `RiskWorkspace` and `App`**

In `WorkspaceViews.tsx`, add these imports:

```ts
import type { RiskShockBridgeModel } from "../utils/riskShockBridge";
import { RiskShockBridge } from "./RiskShockBridge";
```

Replace the `RiskWorkspace` signature with these props, add `/ period {selectedPeriod}` to the heading provenance, and render the bridge after `.risk-summary-band`:

```tsx
export function RiskWorkspace({
  signal,
  subjectName,
  selectedPeriod,
  accessNotice,
  bridge,
  canOpenMatching,
  onOpenMatching,
  onOpenShock
}: {
  signal: RiskSignal | null;
  subjectName: string;
  selectedPeriod: string;
  accessNotice?: string | null;
  bridge: RiskShockBridgeModel | null;
  canOpenMatching: boolean;
  onOpenMatching: () => void;
  onOpenShock: () => void;
}) {
```

```tsx
<header className="workspace-heading">
  <div>
    <span className="eyebrow">{riskEyebrow}</span>
    <h1>Risk Signal Review</h1>
    <p>{subjectName} / period {selectedPeriod} / rule set {signal.formulaVersion}</p>
  </div>
  <span className="confidence-ring"><strong>{signal.confidence}%</strong><small>confidence</small></span>
</header>
```

```tsx
{bridge ? <RiskShockBridge model={bridge} onOpenScenario={onOpenShock} /> : null}
```

In `App.tsx`, add `import { riskShockBridgeModel } from "./utils/riskShockBridge";`. After `selected` is resolved, create the display model:

```ts
const riskSubjectName = selected?.name ?? riskSignal?.businessId ?? selectedId;
const riskShockBridge = useMemo(() => riskSignal ? riskShockBridgeModel({
  signalBusinessId: riskSignal.businessId,
  subjectName: riskSubjectName,
  periodKey: selectedPeriod,
  canRunScenario: dataPermissions.canReadGraph,
  shock
}) : null, [dataPermissions.canReadGraph, riskSignal, riskSubjectName, selectedPeriod, shock]);
```

Use this handler:

```ts
async function handleOpenShock() {
  if (!riskShockBridge || riskShockBridge.action === "none") return;
  if (riskShockBridge.action === "run") await handleSimulate();
  openView("overview");
}
```

Pass the exact props in the Risk render branch and keep the existing Matching callback unchanged:

```tsx
<RiskWorkspace
  signal={riskSignal}
  subjectName={riskSubjectName}
  selectedPeriod={selectedPeriod}
  accessNotice={riskAccessNotice}
  bridge={riskShockBridge}
  canOpenMatching={allowedViewIds.includes("matching")}
  onOpenMatching={() => openView("matching")}
  onOpenShock={handleOpenShock}
/>
```

- [ ] **Step 5: Run focused tests and TypeScript build**

Run: `cd frontend; npm.cmd exec vitest -- run src/utils/riskShockBridge.test.ts src/components/RiskShockBridge.test.tsx --cache=false`

Expected: 6 tests pass.

Run: `cd frontend; npm.cmd run build`

Expected: TypeScript and Vite build exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/RiskShockBridge.tsx frontend/src/components/RiskShockBridge.test.tsx frontend/src/components/WorkspaceViews.tsx frontend/src/App.tsx
git commit -m "Connect risk review to shock scenario"
```

---

### Task 3: Responsive Polish, Demo Script, And Final Verification

**Files:**
- Modify: `frontend/src/styles.css`
- Modify: `docs/21-competition-demo-runbook.md`
- Modify: `PROJECT_STATE.md`

**Interfaces:**
- Consumes: `.risk-shock-bridge`, `.risk-shock-flow`, `.risk-shock-copy`, and `.risk-shock-metrics` DOM classes.
- Produces: desktop/mobile layout and the official presenter handoff instructions.

- [ ] **Step 1: Add compact responsive styles**

Add these base styles next to the existing risk workspace styles:

```css
.risk-shock-bridge { min-width: 0; display: grid; grid-template-columns: minmax(190px, 0.65fr) minmax(260px, 1.15fr) minmax(300px, 1fr) auto; gap: 12px; align-items: center; padding: 12px; border: 1px solid rgba(34, 211, 238, 0.3); border-left: 3px solid var(--amber); border-radius: 7px; background: var(--panel); }
.risk-shock-bridge.live { border-left-color: var(--teal); background: rgba(45, 212, 191, 0.05); }
.risk-shock-bridge.unavailable { border-color: var(--line); border-left-color: var(--muted); }
.risk-shock-flow { min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); gap: 7px; align-items: center; }
.risk-shock-flow > svg { color: var(--muted); }
.risk-shock-flow > span { min-width: 0; display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 2px 6px; align-items: center; padding: 8px; border: 1px solid var(--line); border-radius: 6px; background: var(--panel-2); }
.risk-shock-flow > span > svg { grid-row: 1 / 3; color: var(--red); }
.risk-shock-flow > span:last-child > svg { color: var(--teal); }
.risk-shock-flow small, .risk-shock-flow strong { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.risk-shock-flow small { color: var(--muted); font-size: 8px; text-transform: uppercase; }
.risk-shock-flow strong { font-size: 10px; }
.risk-shock-copy { min-width: 0; }
.risk-shock-copy h2 { margin: 4px 0; font-size: 16px; }
.risk-shock-copy p { margin: 0; color: #d4e1e0; font-size: 10px; line-height: 1.45; }
.risk-shock-copy > small { display: block; margin-top: 5px; color: var(--muted); font-size: 8px; line-height: 1.4; }
.risk-shock-metrics { min-width: 0; display: grid; grid-template-columns: repeat(4, minmax(70px, 1fr)); gap: 6px; }
.risk-shock-metrics > span { min-width: 0; min-height: 48px; display: grid; align-content: center; gap: 3px; padding: 7px; border: 1px solid var(--line); border-radius: 6px; background: var(--panel-2); }
.risk-shock-metrics strong, .risk-shock-metrics small { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.risk-shock-metrics strong { color: var(--cyan); font-size: 11px; }
.risk-shock-metrics small { color: var(--muted); font-size: 8px; }
.risk-shock-bridge > .primary-button { min-width: 190px; justify-content: center; }
```

Inside `@media (max-width: 1220px)`, add:

```css
.risk-shock-bridge { grid-template-columns: minmax(220px, 0.75fr) minmax(0, 1.25fr); }
.risk-shock-metrics { grid-column: 1 / -1; }
.risk-shock-bridge > .primary-button { grid-column: 1 / -1; justify-self: end; }
```

Inside `@media (max-width: 600px)`, add:

```css
.risk-shock-bridge { grid-template-columns: 1fr; }
.risk-shock-metrics { grid-column: auto; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.risk-shock-bridge > .primary-button { grid-column: auto; width: 100%; min-width: 0; justify-self: stretch; }
```

- [ ] **Step 2: Update the official runbook**

Under `Supply Map + Risk`, add: `Use Run operational scenario to hand the evidence-backed signal into the hypothetical network test.`

Under `Shock Simulation`, replace the manual Run instruction with: `The app returns to Overview automatically; let the 2.2-second sequence finish.`

- [ ] **Step 3: Run all frontend gates**

Run: `cd frontend; npm.cmd test -- --run --cache=false`

Expected: all tests pass, including the 6 new bridge tests.

Run: `cd frontend; npm.cmd run build`

Expected: exit 0 with no chunk-size warning.

Run: `cd frontend; npm.cmd run test:bundle`

Expected: bundle budget passes.

- [ ] **Step 4: Browser QA the official route**

Open `http://127.0.0.1:5173/?view=risk&account=demo-operator&business=BIZ-005&period=2026-07`.

Verify on desktop:

- bridge is `ready` and contains no calculated shock values;
- button opens Overview and the presentation reaches `origin`, `propagation`, `impact`, then `recovery`;
- returning to Risk shows bridge state `live` with the returned values;
- no console errors or horizontal overflow.

Verify at `390x844`:

- bridge is one column;
- button text fits;
- no overlap or horizontal overflow.

Reset the browser viewport after QA.

- [ ] **Step 5: Update handoff state and commit**

Add these exact points under `Latest Slice` in `PROJECT_STATE.md`:

```markdown
- Added a policy-safe Risk-to-Shock bridge for the official `BIZ-005` competition path.
- Risk now separates observed evidence from a hypothetical network scenario, hides seeded impact values before execution, and hands the presenter into the staged Overview cinematic.
- Live bridge metrics come only from the returned shock result; Matching remains an independent human-review path.
```

Replace the frontend test count with `111/111`. Replace the browser Shock line with the verified Risk `ready` -> Overview four-phase -> Risk `live` result, and keep the next slice focused on Matching card hierarchy and consent/review actions.

```bash
git add frontend/src/styles.css docs/21-competition-demo-runbook.md PROJECT_STATE.md
git commit -m "Polish risk-to-shock demo handoff"
```

- [ ] **Step 6: Rebase and push**

```bash
git pull --rebase origin main
git push origin main
git status --short --branch
```

Expected: local `main` is clean and synchronized with `origin/main`.
