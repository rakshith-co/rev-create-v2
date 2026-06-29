import React, { useEffect, useState } from "react";
import axios from "axios";
import JSZip from "jszip";
import { ImageOut, ProjectOut, PLATFORM_SIZES } from "../types";
import { requestImageEdit } from "../api";
import SizeVariantModal from "./SizeVariantModal";

interface Props {
  project: ProjectOut;
  variationIndex: number;
  onClose: () => void;
  onEditSubmit: () => void;
  provider?: "gemini" | "openai";
}

export default function ImageDetailPanel({
  project,
  variationIndex,
  onClose,
  onEditSubmit,
  provider,
}: Props) {
  // Separate size variants from the regular version history
  const allVariationImages = project.images.filter(
    (img) => img.generated?.variation_index === variationIndex
  );
  const variationImages = allVariationImages
    .filter((img) => !img.generated?.parent_id)
    .sort((a, b) => (a.generated?.version ?? 1) - (b.generated?.version ?? 1));

  const latestDone = [...variationImages]
    .reverse()
    .find((img) => img.status === "done");
  const latestImg = variationImages[variationImages.length - 1];
  const isWaitingForEdit =
    latestImg &&
    (latestImg.status === "pending" || latestImg.status === "generating");

  const [selectedVersion, setSelectedVersion] = useState<number>(
    latestDone?.generated?.version ?? 1
  );
  const [instruction, setInstruction] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editError, setEditError] = useState("");
  const [showSizeModal, setShowSizeModal] = useState(false);
  const [previewVariantId, setPreviewVariantId] = useState<string | null>(null);

  // Auto-advance to the newest done version when a new edit completes
  useEffect(() => {
    if (latestDone && (latestDone.generated?.version ?? 1) > selectedVersion) {
      setSelectedVersion(latestDone.generated?.version ?? 1);
    }
  }, [latestDone?.generated?.version]);

  const selectedImage = variationImages.find((img) => (img.generated?.version ?? 1) === selectedVersion);

  // Size variants: grouped by platform
  const sizeVariants = project.images.filter(
    (img) => img.generated?.parent_id && img.generated?.variation_index === variationIndex
  );

  // When a size variant is being previewed, show it in the main image slot
  const previewVariant = previewVariantId
    ? sizeVariants.find((v) => v.id === previewVariantId) ?? null
    : null;
  const displayImage = previewVariant ?? selectedImage;

  const [w, h] = project.ad_format.split("x");

  // Resolve dimensions for whatever is currently displayed
  const activeFormat = displayImage 
    ? `${displayImage.metadata.size_specs.width}x${displayImage.metadata.size_specs.height}`
    : project.ad_format;
  const [activeW, activeH] = activeFormat.split("x");
  const displayDimensions = previewVariant?.metadata.size_label ?? project.ad_format;
  
  // Only show variants that belong to the currently selected version
  const selectedVersionVariants = sizeVariants.filter(
    (v) => v.generated?.parent_id === selectedImage?.id
  );
  const variantsByPlatform = selectedVersionVariants.reduce<Record<string, ImageOut[]>>(
    (acc, img) => {
      const key = img.metadata.platform ?? "unknown";
      if (!acc[key]) acc[key] = [];
      acc[key].push(img);
      return acc;
    },
    {}
  );

  const [editJobId, setEditJobId] = useState<string | null>(null);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (editJobId && isSubmitting) {
      interval = setInterval(async () => {
        try {
          const { getJob } = await import("../api");
          const job = await getJob(editJobId);
          if (["done", "failed", "partial_failure"].includes(job.status)) {
            setIsSubmitting(false);
            setEditJobId(null);
            clearInterval(interval);
            onEditSubmit(); // Refresh data to show the new edit
          }
        } catch (e) {
          console.error("Polling error", e);
          setIsSubmitting(false);
          setEditJobId(null);
          clearInterval(interval);
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [editJobId, isSubmitting, onEditSubmit]);

  const handleSend = async () => {
    if (!instruction.trim() || isSubmitting || isWaitingForEdit || !latestDone)
      return;
    setIsSubmitting(true);
    setEditError("");
    setEditJobId(null);
    try {
      const accepted = await requestImageEdit(latestDone.id, instruction.trim(), provider);
      setEditJobId(accepted.job_id);
      setInstruction("");
    } catch (e) {
      setIsSubmitting(false);
      const msg = axios.isAxiosError(e)
        ? e.response?.data?.detail ?? e.message
        : "Edit request failed";
      setEditError(msg);
    }
  };

  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = async () => {
    if (!selectedImage?.creative_url) return;
    setIsDownloading(true);
    try {
      const doneSizeVariants = selectedVersionVariants.filter((v) => v.status === "done" && v.creative_url);
      const zip = new JSZip();

      const apiBase = (import.meta.env.VITE_API_URL || "") + "/api";

      // Main image
      const mainBlob = await fetch(`${apiBase}/images/${selectedImage.id}/download`).then((r) => r.blob());
      zip.file(`var${variationIndex}_v${selectedVersion}.png`, mainBlob);

      // Size variants grouped into platform folders
      await Promise.all(
        doneSizeVariants.map(async (v) => {
          const blob = await fetch(`${apiBase}/images/${v.id}/download`).then((r) => r.blob());
          const folder = v.metadata.platform ?? "variants";
          const name = (v.metadata.size_label ?? "variant").replace(/ \/ /g, "-").replace(/ /g, "_");
          zip.file(`${folder}/${name}.png`, blob);
        })
      );

      const zipBlob = await zip.generateAsync({ type: "blob" });
      const objectUrl = URL.createObjectURL(zipBlob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = `variation_${variationIndex}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-50 flex">
        {/* Backdrop */}
        <div className="flex-1 bg-black/60" onClick={onClose} />

        {/* Panel */}
        <div className="w-[500px] flex-shrink-0 bg-gray-900 border-l border-gray-800 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 flex-shrink-0">
            <div>
              <h3 className="text-sm font-semibold text-white">
                {previewVariant ? previewVariant.metadata.size_label : `Variation ${variationIndex}`}
              </h3>
              <p className="text-xs text-gray-500 mt-0.5">
                {displayDimensions}
                {!previewVariant && ` · ${w}×${h}px`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {previewVariant ? (
                <button
                  onClick={() => setPreviewVariantId(null)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-800 hover:bg-gray-700
                             text-gray-300 border border-gray-700 transition"
                >
                  ← Back
                </button>
              ) : selectedImage?.status === "done" && (
                <>
                  <button
                    onClick={() => setShowSizeModal(true)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-violet-600 hover:bg-violet-500
                               text-white border border-violet-500 transition"
                  >
                    Size Variants
                  </button>
                </>
              )}
              {selectedImage?.status === "done" && (
                <button
                  onClick={handleDownload}
                  disabled={isDownloading}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-800 hover:bg-gray-700
                             text-gray-300 border border-gray-700 transition disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {isDownloading ? "Zipping…" : "Download"}
                </button>
              )}
              <button
                onClick={onClose}
                className="text-gray-500 hover:text-gray-300 transition p-1"
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
          </div>

          {/* Scrollable content */}
          <div className="flex-1 overflow-y-auto">
            {/* Main image */}
            <div className="p-5">
              {displayImage?.status === "done" && displayImage.creative_url ? (
                <img
                  src={displayImage.creative_url}
                  alt={previewVariant ? (previewVariant.metadata.size_label ?? "") : `Variation ${variationIndex} v${selectedVersion}`}
                  className="w-full rounded-xl border border-gray-700 object-contain"
                />
              ) : displayImage && (displayImage.status === "pending" || displayImage.status === "generating" || displayImage.status === "retrying") ? (
                <div className="aspect-square rounded-xl border border-gray-700 bg-gray-800 flex flex-col items-center justify-center gap-2">
                  <svg className="animate-spin h-5 w-5 text-violet-400" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <p className="text-xs text-gray-500">Generating…</p>
                </div>
              ) : (
                <div className="aspect-square rounded-xl border border-gray-700 bg-gray-800 flex items-center justify-center">
                  <p className="text-xs text-gray-500">No image</p>
                </div>
              )}
            </div>

            {/* Version thumbnails */}
            {variationImages.length > 0 && (
              <div className="px-5 pb-5">
                <p className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wider">
                  Versions
                </p>
                <div className="flex gap-2 flex-wrap">
                  {variationImages.map((img) => (
                    <VersionThumb
                      key={img.id}
                      image={img}
                      isSelected={selectedVersion === (img.generated?.version ?? 1) && !previewVariantId}
                      onClick={() => {
                        if (img.status === "done") {
                          setSelectedVersion(img.generated?.version ?? 1);
                          setPreviewVariantId(null);
                        }
                      }}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Size details */}
            <div className="px-5 pb-5">
              <p className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wider">
                Size Details
              </p>
              <div className="bg-gray-800 rounded-lg p-3 text-xs space-y-1.5">
                {[
                  ["Format", activeFormat],
                  ["Width", `${activeW}px`],
                  ["Height", `${activeH}px`],
                  ...(displayImage?.metadata.platform
                    ? [["Platform", PLATFORM_SIZES[displayImage.metadata.platform]?.label ?? displayImage.metadata.platform]]
                    : []),
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-gray-500">{label}</span>
                    <span className="text-gray-200">{val}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Edit history */}
            {variationImages.some((img) => img.generated?.edit_instruction) && (
              <div className="px-5 pb-5">
                <p className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wider">
                  Edit History
                </p>
                <div className="space-y-2">
                  {variationImages
                    .filter((img) => img.generated?.edit_instruction)
                    .map((img) => (
                      <div
                        key={img.id}
                        className="bg-gray-800 rounded-lg px-3 py-2 text-xs text-gray-300"
                      >
                        <span className="text-gray-500 mr-2">v{img.generated?.version}:</span>
                        {img.generated?.edit_instruction}
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Size variants */}
            {Object.keys(variantsByPlatform).length > 0 && (
              <div className="px-5 pb-5">
                <p className="text-xs font-medium text-gray-500 mb-3 uppercase tracking-wider">
                  Size Variants
                </p>
                <div className="space-y-4">
                  {Object.entries(variantsByPlatform).map(([platformKey, variants]) => (
                    <div key={platformKey}>
                      <p className="text-xs font-medium text-gray-400 mb-2">
                        {PLATFORM_SIZES[platformKey]?.label ?? platformKey}
                      </p>
                      <div className="space-y-2">
                        {variants.map((variant) => (
                          <SizeVariantRow
                            key={variant.id}
                            variant={variant}
                            isSelected={previewVariantId === variant.id}
                            onSelect={() =>
                              variant.status === "done" &&
                              setPreviewVariantId(
                                previewVariantId === variant.id ? null : variant.id
                              )
                            }
                          />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Meta Platform Copy */}
            {selectedImage?.ad_copy?.platforms?.meta && (() => {
              const meta = selectedImage.ad_copy!.platforms!.meta!;
              const toArr = (v: string | string[]) => Array.isArray(v) ? v : [v];
              const primaryTexts = toArr(meta.primary_text);
              const headlines = toArr(meta.headline);
              const descriptions = toArr(meta.description);
              return (
                <div className="px-5 pb-10">
                  <p className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wider">
                    Meta Ad Platform Copy
                  </p>
                  <div className="bg-violet-950/20 border border-violet-800/30 rounded-xl p-4 space-y-4">
                    {/* Primary Text */}
                    <div>
                      <p className="text-[10px] font-bold text-violet-500 uppercase tracking-widest mb-2">Primary Text</p>
                      <div className="space-y-2">
                        {primaryTexts.map((text, idx) => (
                          <div key={idx} className="flex gap-2">
                            <span className="text-[9px] font-bold text-violet-400/50 mt-0.5 shrink-0">V{idx + 1}</span>
                            <div className="flex-1">
                              <p className="text-gray-300 text-xs leading-relaxed whitespace-pre-wrap">{text}</p>
                              <span className={`text-[9px] font-medium ${text.length > 125 ? 'text-orange-400' : 'text-violet-400/40'}`}>{text.length}/125</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                    {/* Headline */}
                    <div className="pt-3 border-t border-violet-800/20">
                      <p className="text-[10px] font-bold text-violet-500 uppercase tracking-widest mb-2">Headline</p>
                      <div className="space-y-1.5">
                        {headlines.map((text, idx) => (
                          <div key={idx} className="flex gap-2 items-baseline">
                            <span className="text-[9px] font-bold text-violet-400/50 shrink-0">V{idx + 1}</span>
                            <p className="text-white text-xs font-bold flex-1">{text}</p>
                            <span className={`text-[9px] font-medium shrink-0 ${text.length > 40 ? 'text-orange-400' : 'text-violet-400/40'}`}>{text.length}/40</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    {/* Description */}
                    <div className="pt-3 border-t border-violet-800/20">
                      <p className="text-[10px] font-bold text-violet-500 uppercase tracking-widest mb-2">Description</p>
                      <div className="space-y-1.5">
                        {descriptions.map((text, idx) => (
                          <div key={idx} className="flex gap-2 items-baseline">
                            <span className="text-[9px] font-bold text-violet-400/50 shrink-0">V{idx + 1}</span>
                            <p className="text-gray-400 text-[11px] leading-tight flex-1">{text}</p>
                            <span className={`text-[9px] font-medium shrink-0 ${text.length > 25 ? 'text-orange-400' : 'text-violet-400/40'}`}>{text.length}/25</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    {/* CTA */}
                    <div className="pt-3 border-t border-violet-800/20">
                      <p className="text-[10px] font-bold text-violet-500 uppercase tracking-widest mb-1">Call to Action</p>
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-violet-600/30 text-violet-200 border border-violet-500/30">
                        {meta.call_to_action}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>

          {/* Edit chat input */}
          <div className="flex-shrink-0 border-t border-gray-800 p-4 space-y-2">
            {isWaitingForEdit && (
              <div className="flex items-center gap-2 text-xs text-violet-400">
                <svg
                  className="animate-spin h-3 w-3"
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
                Generating edited image…
              </div>
            )}
            {editError && <p className="text-xs text-red-400">{editError}</p>}
            <div className="flex gap-2">
              <input
                className="input flex-1 text-sm"
                placeholder="Describe an edit (e.g. make background blue)…"
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                disabled={!!isWaitingForEdit || isSubmitting}
              />
              <button
                onClick={handleSend}
                disabled={
                  !instruction.trim() || !!isWaitingForEdit || isSubmitting
                }
                className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium
                           disabled:opacity-40 disabled:cursor-not-allowed transition flex-shrink-0"
              >
                {isSubmitting ? "…" : "Send"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Size variant modal — rendered outside the panel so it overlays cleanly */}
      {showSizeModal && latestDone && (
        <SizeVariantModal
          imageId={latestDone.id}
          provider={provider}
          onClose={() => setShowSizeModal(false)}
          onGenerated={() => {
            setShowSizeModal(false);
            onEditSubmit();
          }}
        />
      )}
    </>
  );
}

function VersionThumb({
  image,
  isSelected,
  onClick,
}: {
  image: ImageOut;
  isSelected: boolean;
  onClick: () => void;
}) {
  const version = image.generated?.version ?? 1;
  return (
    <button
      onClick={onClick}
      disabled={image.status !== "done"}
      className={[
        "relative h-14 w-14 rounded-lg border overflow-hidden transition",
        isSelected ? "border-violet-500" : "border-gray-700",
        image.status !== "done" ? "cursor-not-allowed" : "cursor-pointer",
      ].join(" ")}
    >
      {image.status === "done" && image.creative_url ? (
        <img
          src={image.creative_url}
          alt={`v${version}`}
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="w-full h-full bg-gray-800 flex items-center justify-center">
          {image.status === "failed" ? (
            <span className="text-red-400 text-xs">!</span>
          ) : (
            <svg
              className="animate-spin h-3 w-3 text-violet-400"
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
        </div>
      )}
      <span className="absolute bottom-0 left-0 right-0 text-center text-xs bg-black/70 text-gray-300 leading-4 py-0.5">
        v{version}
      </span>
    </button>
  );
}

function SizeVariantRow({
  variant,
  isSelected,
  onSelect,
}: {
  variant: ImageOut;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      className={[
        "flex items-center gap-3 rounded-lg p-2.5 border transition",
        variant.status === "done" ? "cursor-pointer" : "cursor-default",
        isSelected
          ? "bg-violet-500/10 border-violet-500"
          : "bg-gray-800 border-gray-700 hover:border-gray-600",
      ].join(" ")}
    >
      {/* Thumbnail */}
      <div className="h-12 w-12 flex-shrink-0 rounded-md border border-gray-700 overflow-hidden bg-gray-700 flex items-center justify-center">
        {variant.status === "done" && variant.creative_url ? (
          <img
            src={variant.creative_url}
            alt={variant.metadata.size_label ?? ""}
            className="w-full h-full object-cover"
          />
        ) : variant.status === "failed" ? (
          <span className="text-red-400 text-xs">!</span>
        ) : (
          <svg
            className="animate-spin h-3 w-3 text-violet-400"
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
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        )}
      </div>

      {/* Label + dimensions */}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-white truncate">
          {variant.metadata.size_label}
        </p>
        {variant.status === "failed" ? (
          <p className="text-xs text-red-400 mt-0.5 truncate">
            {variant.error_message ?? "Failed"}
          </p>
        ) : (
          <p className="text-xs text-gray-500 mt-0.5 capitalize">
            {variant.status === "done" ? "Ready" : variant.status}
          </p>
        )}
      </div>

      {/* Download */}
    </div>
  );
}
