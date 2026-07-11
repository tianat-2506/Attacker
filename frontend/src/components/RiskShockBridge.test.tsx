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
  guardrail: "Hypothetical decision-support scenario. Not a forecast, legal finding, or supplier replacement instruction.",
  riskNotice: "Advisory risk signal. Not a credit assessment or legal/compliance breach determination. No supplier is selected or replaced automatically.",
  provenance: null,
  unavailableReason: null
};

describe("RiskShockBridge", () => {
  it("renders a stable ready-state handoff without inventing a result", () => {
    const html = renderToStaticMarkup(<RiskShockBridge model={ready} onOpenScenario={vi.fn()} />);

    expect(html).toContain('data-testid="risk-shock-bridge"');
    expect(html).toContain('data-state="ready"');
    expect(html).toContain("Run operational scenario");
    expect(html).toContain("Not a forecast");
    expect(html).toContain("Not a credit assessment");
  });

  it("disables an unavailable scenario action", () => {
    const html = renderToStaticMarkup(
      <RiskShockBridge
        model={{ ...ready, state: "unavailable", action: "none", actionLabel: "Scenario unavailable", disabled: true, unavailableReason: "shock_execution_denied" }}
        onOpenScenario={vi.fn()}
      />
    );

    expect(html).toContain("disabled");
  });

  it("renders result provenance while keeping the scenario hypothetical", () => {
    const html = renderToStaticMarkup(
      <RiskShockBridge
        model={{
          ...ready,
          state: "result",
          eyebrow: "Hypothetical scenario result",
          action: "open",
          actionLabel: "View scenario results",
          provenance: "run SCN-001 / period 2026-07 / policy POL-001 / audit AUD-001"
        }}
        onOpenScenario={vi.fn()}
      />
    );

    expect(html).toContain('data-state="result"');
    expect(html).toContain("Hypothetical scenario result");
    expect(html).toContain("SCN-001");
    expect(html).toContain("POL-001");
  });
});
