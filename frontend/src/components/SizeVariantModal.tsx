import React, { useState } from "react";
import axios from "axios";
import { PLATFORM_SIZES } from "../types";
import { requestSizeVariants } from "../api";

interface Props {
  imageId: string;
  onClose: () => void;
  onGenerated: () => void;
  provider?: "gemini" | "openai";
}

const PREVIEW_MAX = 72;

function SizePreviewBox({ dimensions }: { dimensions: string }) {
  const [w, h] = dimensions.split("x").map(Number);
  const ratio = w / h;
  let pw: number, ph: number;
  if (ratio >= 1) {
    pw = PREVIEW_MAX;
    ph = Math.max(6, Math.round(PREVIEW_MAX / ratio));
  } else {
    ph = PREVIEW_MAX;
    pw = Math.max(6, Math.round(PREVIEW_MAX * ratio));
  }
  return (
    <div
      className="border border-violet-500 bg-violet-500/10 rounded"
      style={{ width: pw, height: ph }}
    />
  );
}

export default function SizeVariantModal({ imageId, onClose, onGenerated, provider }: Props) {
  const [selectedPlatform, setSelectedPlatform] = useState<string>("meta");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const platformConfig = PLATFORM_SIZES[selectedPlatform];

  const handleGenerate = async () => {
    setIsSubmitting(true);
    setError("");
    try {
      await requestSizeVariants(imageId, selectedPlatform, undefined, undefined, provider);
      onGenerated();
    } catch (e) {
      const msg = axios.isAxiosError(e)
        ? e.response?.data?.detail ?? e.message
        : "Failed to queue size variants";
      setError(msg);
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70"
        onClick={!isSubmitting ? onClose : undefined}
      />

      {/* Modal */}
      <div className="relative bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-[480px] max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <h2 className="text-sm font-semibold text-white">Generate Size Variants</h2>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="text-gray-500 hover:text-gray-300 transition disabled:opacity-40"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Platform selector */}
          <div>
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">
              Ad Platform
            </p>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(PLATFORM_SIZES).map(([key, config]) => (
                <button
                  key={key}
                  onClick={() => setSelectedPlatform(key)}
                  className={[
                    "px-4 py-3 rounded-xl border text-sm font-medium transition text-left",
                    selectedPlatform === key
                      ? "border-violet-500 bg-violet-500/10 text-violet-300"
                      : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600 hover:text-gray-300",
                  ].join(" ")}
                >
                  {config.label}
                </button>
              ))}
            </div>
          </div>

          {/* Size previews */}
          <div>
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">
              Sizes to generate ({platformConfig.sizes.length})
            </p>
            <div className="grid grid-cols-2 gap-3">
              {platformConfig.sizes.map((size) => (
                <div
                  key={size.dimensions}
                  className="bg-gray-800 rounded-xl p-3 border border-gray-700 flex items-center gap-3"
                >
                  <div className="flex items-center justify-center w-20 h-20 flex-shrink-0">
                    <SizePreviewBox dimensions={size.dimensions} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-white truncate">{size.label}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{size.dimensions}px</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {error && <p className="text-xs text-red-400">{error}</p>}

          {/* Generate button */}
          <button
            onClick={handleGenerate}
            disabled={isSubmitting}
            className="w-full py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium
                       disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {isSubmitting
              ? "Queuing…"
              : `Generate ${platformConfig.sizes.length} variants`}
          </button>
        </div>
      </div>
    </div>
  );
}
