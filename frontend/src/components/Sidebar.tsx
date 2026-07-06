import { Building2, Landmark, Package } from "lucide-react";
import type { BusinessNode, OverviewMetrics, Recommendation, RiskDriver, ShockState } from "../types";
import { RecommendationCard } from "./RecommendationCard";
import { RiskPanel } from "./RiskPanel";
import { ShockSimulationButton } from "./ShockSimulationButton";

interface SidebarProps {
  selected: BusinessNode;
  shock: ShockState;
  drivers: RiskDriver[];
  recommendations: Recommendation[];
  overview: OverviewMetrics;
  onSimulate: () => void;
  onReset: () => void;
}

export function Sidebar({ selected, shock, drivers, recommendations, overview, onSimulate, onReset }: SidebarProps) {
  return (
    <aside className="sidebar">
      <section className="business-summary">
        <div className="business-icon">
          <Building2 size={22} />
        </div>
        <div>
          <h1>{selected.name}</h1>
          <p>{selected.type.replace("_", " ")} - {selected.province}</p>
        </div>
      </section>

      <div className="metric-grid">
        <div className="metric">
          <Package size={16} />
          <span>Capacity</span>
          <strong>{selected.capacity.toLocaleString()}</strong>
        </div>
        <div className="metric">
          <Landmark size={16} />
          <span>Revenue</span>
          <strong>{selected.revenue.toFixed(2)}B</strong>
        </div>
      </div>

      <ShockSimulationButton active={shock.active} onSimulate={onSimulate} onReset={onReset} />

      <RiskPanel node={selected} drivers={drivers} />

      <section className="panel-section">
        <div className="section-title">
          <Package size={17} />
          <span>Impact</span>
        </div>
        <div className="impact-grid">
          <div>
            <strong>{shock.active ? shock.affectedSmeCount : 0}</strong>
            <span>SMEs</span>
          </div>
          <div>
            <strong>{shock.active ? shock.monthlyVolumeAtRisk.toLocaleString() : 0}</strong>
            <span>units/month</span>
          </div>
          <div>
            <strong>{shock.active ? shock.avgStockoutDays.toFixed(1) : "0.0"}</strong>
            <span>stockout days</span>
          </div>
        </div>
      </section>

      <section className="panel-section recommendations">
        <div className="section-title">
          <Package size={17} />
          <span>Supplier Shortlist</span>
        </div>
        {recommendations.map((recommendation) => (
          <RecommendationCard key={recommendation.supplierId} recommendation={recommendation} />
        ))}
      </section>

      <section className="panel-section advisory-panel">
        <strong>Advisory guardrail</strong>
        <p>{shock.advisoryNotice ?? overview.advisoryNotice}</p>
      </section>
    </aside>
  );
}
