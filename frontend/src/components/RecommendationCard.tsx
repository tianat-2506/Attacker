import { CheckCircle2, Truck } from "lucide-react";
import type { Recommendation } from "../types";

interface RecommendationCardProps {
  recommendation: Recommendation;
}

export function RecommendationCard({ recommendation }: RecommendationCardProps) {
  return (
    <article className="recommendation-card">
      <div className="recommendation-head">
        <div>
          <h3>{recommendation.supplierName}</h3>
          <span>{recommendation.leadTimeDays} days lead time</span>
        </div>
        <div className="match-score">{recommendation.score}</div>
      </div>
      <div className="reason-list">
        {recommendation.reasons.map((reason) => (
          <span key={reason}>
            <CheckCircle2 size={14} />
            {reason}
          </span>
        ))}
      </div>
      <button className="icon-text-button" type="button" aria-label={`Preview route for ${recommendation.supplierName}`}>
        <Truck size={16} />
        <span>Request intro</span>
      </button>
    </article>
  );
}
