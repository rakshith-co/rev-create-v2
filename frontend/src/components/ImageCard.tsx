import React from "react";
import { ImageOut } from "../types";

interface Props {
  variationIndex: number;
  image?: ImageOut;
  onClick: () => void;
}

export default function ImageCard({ variationIndex, image, onClick }: Props) {
  const isDone = image?.status === "done";
  const isFailed = image?.status === "failed";
  const isGenerating = image?.status === "generating";

  return (
    <div
      onClick={isDone ? onClick : undefined}
      className={[
        "relative rounded-xl border overflow-hidden bg-gray-900 aspect-square transition",
        isDone
          ? "border-gray-700 cursor-pointer hover:border-violet-500 group"
          : "border-gray-800",
      ].join(" ")}
    >
      {isDone && image?.creative_url ? (
        <>
          <img
            src={image.creative_url}
            alt={`Variation ${variationIndex}`}
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition flex items-center justify-center">
            <span className="opacity-0 group-hover:opacity-100 transition text-white text-xs font-semibold bg-black/60 px-3 py-1.5 rounded-full">
              Open
            </span>
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center justify-center h-full gap-2 text-xs text-gray-500">
          {isFailed ? (
            <span className="text-red-400">Generation failed</span>
          ) : (
            <>
              <svg
                className="animate-spin h-5 w-5 text-violet-500"
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
              <span>{isGenerating ? "Generating…" : "Pending…"}</span>
            </>
          )}
        </div>
      )}

      <span className="absolute top-2 left-2 text-xs bg-black/60 text-gray-300 px-2 py-0.5 rounded-full">
        Var {variationIndex}
      </span>
    </div>
  );
}
