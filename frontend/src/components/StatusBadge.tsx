import React from "react";

const CONFIG: Record<string, { label: string; cls: string }> = {
  pending: { label: "Pending", cls: "bg-gray-700 text-gray-400" },
  generating_copy: { label: "Generating copy…", cls: "bg-yellow-900/60 text-yellow-400" },
  generating_images: { label: "Generating images…", cls: "bg-blue-900/60 text-blue-400" },
  generating: { label: "Generating…", cls: "bg-blue-900/60 text-blue-400" },
  retrying: { label: "Retrying…", cls: "bg-orange-900/60 text-orange-400" },
  ready: { label: "Ready", cls: "bg-green-900/60 text-green-400" },
  done: { label: "Done", cls: "bg-green-900/60 text-green-400" },
  failed: { label: "Failed", cls: "bg-red-900/60 text-red-400" },
  stopped: { label: "Stopped", cls: "bg-gray-700 text-gray-400" },
};

export default function StatusBadge({ status }: { status: string }) {
  const cfg = CONFIG[status] ?? { label: status, cls: "bg-gray-700 text-gray-400" };
  const spinning =
    status === "generating_copy" ||
    status === "generating_images" ||
    status === "generating" ||
    status === "retrying" ||
    status === "pending";

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${cfg.cls}`}
    >
      {spinning && (
        <svg
          className="animate-spin h-2.5 w-2.5"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v8H4z"
          />
        </svg>
      )}
      {cfg.label}
    </span>
  );
}
