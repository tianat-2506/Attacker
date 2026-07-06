import { AlertTriangle, TrendingDown } from "lucide-react";
import type { BusinessNode, RiskDriver } from "../types";

interface RiskPanelProps {
  node: BusinessNode;
  drivers: RiskDriver[];
}

function levelLabel(risk: number) {
  if (risk >= 70) return "High";
  if (risk >= 45) return "Watch";
  return "Low";
}

export function RiskPanel({ node, drivers }: RiskPanelProps) {
  return (
    <section className="panel-section">
      <div className="section-title">
        <AlertTriangle size={17} />
        <span>Risk Signal</span>
      </div>
      <div className="risk-score-row">
        <div className={`risk-orb ${node.risk >= 70 ? "risk-red" : node.risk >= 45 ? "risk-amber" : "risk-green"}`}>
          {node.risk}
        </div>
        <div>
          <div className="risk-level">{levelLabel(node.risk)}</div>
          <div className="muted">Supply Chain Risk Signal</div>
        </div>
      </div>
      <div className="driver-list">
        {drivers.map((driver) => (
          <div className="driver-row" key={driver.label}>
            <TrendingDown size={15} />
            <div>
              <strong>{driver.label}</strong>
              <span>{driver.note}</span>
            </div>
            <b>{driver.value}</b>
          </div>
        ))}
      </div>
    </section>
  );
}
