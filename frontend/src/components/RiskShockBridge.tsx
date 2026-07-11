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
        <small className="risk-shock-risk-notice">{model.riskNotice}</small>
        <small className="risk-shock-guardrail">{model.guardrail}</small>
        {model.provenance ? <code className="risk-shock-provenance">{model.provenance}</code> : null}
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
