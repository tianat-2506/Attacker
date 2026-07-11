import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { businesses, defaultShock, edges } from "../utils/demoData";
import { OverviewWorkspace } from "./WorkspaceViews";

vi.mock("./MapView", () => ({
  MapView: () => <div data-testid="map-view" />
}));

const dashboard = {
  overview: {
    activeCompanies: 62,
    atRiskNodes: 8,
    affectedSmes: 12,
    supplyHealthScore: 74,
    monthlyNetworkVolume: 250000,
    advisoryNotice: "Synthetic demo data."
  },
  disruptionTrend: [
    { month: "2026-06", total: 2, highCritical: 1 },
    { month: "2026-07", total: 3, highCritical: 2 }
  ],
  regionalFlow: [],
  recentAlerts: [],
  riskyBusinesses: businesses.slice(0, 2),
  dataScope: "Synthetic demo data."
};

const scenario = {
  id: "SCN-TEST",
  name: "Test network",
  nodes: businesses,
  edges,
  roleCoverage: {},
  dataScope: "Synthetic demo data."
};

describe("OverviewWorkspace shock execution boundary", () => {
  it("disables every overview shock action when the account lacks simulation capability", () => {
    const html = renderToStaticMarkup(
      <OverviewWorkspace
        dashboard={dashboard}
        allNodes={businesses}
        allEdges={edges}
        scenario={scenario}
        focused
        selectedId="BIZ-005"
        shock={defaultShock}
        recommendations={[]}
        canSimulateShock={false}
        onFocusedChange={vi.fn()}
        onSelect={vi.fn()}
        onSimulate={vi.fn()}
        onReset={vi.fn()}
        canOpenIntake
        onOpenIntake={vi.fn()}
        canOpenRisk
        onOpenRisk={vi.fn()}
        canOpenMatching
        onOpenMatching={vi.fn()}
        canOpenAudit
        onOpenAudit={vi.fn()}
      />
    );

    expect(html).toContain('data-testid="shock-run-story"');
    expect(html).toContain('data-testid="shock-run-primary"');
    expect(html).toMatch(/data-testid="shock-run-story"[^>]*disabled/);
    expect(html).toMatch(/data-testid="shock-run-primary"[^>]*disabled/);
    expect(html).toContain("Scenario execution is not permitted for this account.");
  });
});
