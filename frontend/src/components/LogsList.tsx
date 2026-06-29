import React from "react";
import { LogSummary } from "../types";

interface Props {
  logs: LogSummary[];
  onSelect: (log: LogSummary) => void;
}

function ScorePill({ score }: { score: number | null }) {
  if (score === null) return <span className="text-gray-600">—</span>;
  const color =
    score >= 8 ? "text-green-400" : score >= 5 ? "text-yellow-400" : "text-red-400";
  return <span className={`font-semibold ${color}`}>{score}/10</span>;
}

function avgScore(log: LogSummary): number | null {
  const scored = log.eval.criteria.filter((c) => c.score !== null);
  if (scored.length === 0) return null;
  return Math.round((scored.reduce((s, c) => s + (c.score ?? 0), 0) / scored.length) * 10) / 10;
}

export default function LogsList({ logs, onSelect }: Props) {
  if (logs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-600">
        <p className="text-sm">No logs yet. Logs are created after each completed pipeline run.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {logs.map((log) => {
        const avg = avgScore(log);
        const scoredCount = log.eval.criteria.filter((c) => c.score !== null).length;
        return (
          <button
            key={log.id}
            onClick={() => onSelect(log)}
            className="w-full text-left bg-gray-900 hover:bg-gray-800 border border-gray-800 hover:border-gray-700 rounded-xl px-5 py-4 transition group"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-200 truncate">{log.project_name}</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {log.inputs.product_name} · {log.inputs.ad_format}
                </p>
                {log.ad_copy.headline && (
                  <p className="text-xs text-violet-400 mt-1.5 italic truncate">
                    "{log.ad_copy.headline}"
                  </p>
                )}
              </div>
              <div className="flex-shrink-0 flex flex-col items-end gap-1.5">
                <div className="text-xs text-gray-500">
                  {new Date(log.created_at).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-gray-600">{log.image_count} images</span>
                  <span className="text-gray-600">{scoredCount}/{log.eval.criteria.length} scored</span>
                  <span>Avg: <ScorePill score={avg} /></span>
                </div>
              </div>
            </div>
            {/* Criteria score row */}
            <div className="flex gap-3 mt-3 flex-wrap">
              {log.eval.criteria.map((c) => (
                <span key={c.name} className="text-xs text-gray-500">
                  {c.name}: <ScorePill score={c.score} />
                </span>
              ))}
            </div>
          </button>
        );
      })}
    </div>
  );
}
