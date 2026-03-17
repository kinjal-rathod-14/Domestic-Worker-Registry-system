/**
 * RiskBadge — visual indicator for Low / Medium / High risk levels.
 * Used on dashboards, worker lists, and review queues.
 */

import React from "react";

type RiskLevel = "low" | "medium" | "high";

interface RiskBadgeProps {
  level: RiskLevel;
  score?: number;
  showScore?: boolean;
}

const RISK_CONFIG: Record<RiskLevel, { label: string; classes: string }> = {
  low: {
    label: "Low Risk",
    classes: "bg-green-100 text-green-800 border border-green-200",
  },
  medium: {
    label: "Medium Risk",
    classes: "bg-yellow-100 text-yellow-800 border border-yellow-200",
  },
  high: {
    label: "High Risk",
    classes: "bg-red-100 text-red-800 border border-red-200",
  },
};

export const RiskBadge: React.FC<RiskBadgeProps> = ({
  level,
  score,
  showScore = false,
}) => {
  const config = RISK_CONFIG[level] ?? RISK_CONFIG.medium;

  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${config.classes}`}
      role="status"
      aria-label={`Risk level: ${config.label}${showScore && score !== undefined ? `, score ${score}` : ""}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          level === "low" ? "bg-green-500" :
          level === "medium" ? "bg-yellow-500" : "bg-red-500"
        }`}
      />
      {config.label}
      {showScore && score !== undefined && (
        <span className="ml-1 opacity-70">({score}/100)</span>
      )}
    </span>
  );
};

export default RiskBadge;
