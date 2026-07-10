import { useEffect, useState } from "react";
import { startShockPresentation, type ShockPresentationPhase } from "../utils/shockPresentation";

export function useShockPresentation(active: boolean): ShockPresentationPhase {
  const [phase, setPhase] = useState<ShockPresentationPhase>("baseline");

  useEffect(() => {
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    return startShockPresentation({
      active,
      reducedMotion,
      onPhase: setPhase,
      scheduler: {
        schedule: (callback, delayMs) => window.setTimeout(callback, delayMs),
        clear: (timerId) => window.clearTimeout(timerId)
      }
    });
  }, [active]);

  return phase;
}
