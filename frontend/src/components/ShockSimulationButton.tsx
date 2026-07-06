import { RotateCcw, Zap } from "lucide-react";

interface ShockSimulationButtonProps {
  active: boolean;
  onSimulate: () => void;
  onReset: () => void;
}

export function ShockSimulationButton({ active, onSimulate, onReset }: ShockSimulationButtonProps) {
  return (
    <div className="shock-actions">
      <button className="primary-action" type="button" onClick={onSimulate} disabled={active} aria-label="Simulate supply shock">
        <Zap size={17} />
        <span>Simulate Shock</span>
      </button>
      <button className="icon-button" type="button" onClick={onReset} aria-label="Reset shock">
        <RotateCcw size={17} />
      </button>
    </div>
  );
}
