import type { ShockState } from "../types";

export type ShockPresentationPhase = "baseline" | "origin" | "propagation" | "impact" | "recovery";

export const SHOCK_PHASE_SCHEDULE: ReadonlyArray<{
  phase: Exclude<ShockPresentationPhase, "baseline">;
  delayMs: number;
}> = [
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
