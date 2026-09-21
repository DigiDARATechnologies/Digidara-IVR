import type { CSSProperties } from "react";

export function ScoreGauge({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <div className="score-gauge" style={{ "--score": `${clamped}%` } as CSSProperties}>
      <div className="score-gauge-inner">
        <span>{clamped}</span>
        <small>/100</small>
      </div>
    </div>
  );
}
