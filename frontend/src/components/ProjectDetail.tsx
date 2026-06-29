import React, { useState, useRef, useEffect } from "react";
import { ImageOut, ProjectOut, PLATFORM_SIZES } from "../types";
import { projectDownloadUrl } from "../api";
import ImageCard from "./ImageCard";
import StatusBadge from "./StatusBadge";

function latestPerVariation(images: ImageOut[]): Record<number, ImageOut> {
  const map: Record<number, ImageOut> = {};
  for (const img of images) {
    // Skip size variants and uploads for the main project grid
    if (img.generated?.parent_id || img.source === "uploaded") continue;
    
    const vi = img.generated?.variation_index;
    if (vi === undefined) continue;
    
    const cur = map[vi];
    const version = img.generated?.version ?? 1;
    const curVersion = cur?.generated?.version ?? 0;
    
    if (!cur || version > curVersion) map[vi] = img;
  }
  return map;
}

interface Props {
  project: ProjectOut;
  onImageClick: (variationIndex: number) => void;
  onStop: () => void;
  onRegenerate: () => void;
  isPolling: boolean;
}

export default function ProjectDetail({ project, onImageClick, onStop, onRegenerate, isPolling }: Props) {
  const latest = latestPerVariation(project.images);
  const isReady = project.status === "ready";
  const isDone = project.status === "ready" || project.status === "failed" || project.status === "stopped";

  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setDownloadMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const availablePlatforms = Array.from(
    new Set(project.images.filter(img => img.status === "done" && img.metadata.platform).map(img => img.metadata.platform))
  ) as string[];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white leading-tight">
            {project.name}
          </h2>
          <div className="flex items-center gap-2 mt-1.5">
            <StatusBadge status={project.status} />
            <span className="text-xs text-gray-600">{project.ad_format}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isPolling && (
            <button
              onClick={onStop}
              className="flex-shrink-0 px-4 py-2 rounded-lg text-sm font-medium
                         bg-gray-800 hover:bg-red-900/60 text-gray-400 hover:text-red-300
                         border border-gray-700 hover:border-red-700 transition"
            >
              Stop
            </button>
          )}
          {isDone && (
            <button
              onClick={onRegenerate}
              className="flex-shrink-0 px-4 py-2 rounded-lg text-sm font-medium
                         bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 transition"
            >
              Regenerate
            </button>
          )}
          {isReady && (
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setDownloadMenuOpen(!downloadMenuOpen)}
                className="flex items-center gap-1.5 flex-shrink-0 px-4 py-2 rounded-lg text-sm font-medium
                           bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 transition"
              >
                Download (.zip)
                <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              
              {downloadMenuOpen && (
                <div className="absolute right-0 mt-2 w-48 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-10 py-1 overflow-hidden">
                  <a
                    href={projectDownloadUrl(project.id)}
                    download
                    onClick={() => setDownloadMenuOpen(false)}
                    className="block px-4 py-2.5 text-sm text-gray-200 hover:bg-violet-600/20 hover:text-violet-300 transition"
                  >
                    Download All
                  </a>
                  {availablePlatforms.map((platform) => {
                    const label = PLATFORM_SIZES[platform]?.label || platform;
                    return (
                      <a
                        key={platform}
                        href={projectDownloadUrl(project.id, platform)}
                        download
                        onClick={() => setDownloadMenuOpen(false)}
                        className="block px-4 py-2.5 text-sm text-gray-200 hover:bg-violet-600/20 hover:text-violet-300 transition border-t border-gray-700/50"
                      >
                        {label} Variants
                      </a>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Error */}
      {project.status === "failed" && project.error_message && (
        <div className="bg-red-900/40 border border-red-800 rounded-lg px-4 py-3 text-sm text-red-300">
          {project.error_message}
        </div>
      )}

      {/* Image grid */}
      <div className="max-w-[60%] mx-auto">
        <div className="grid grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((vi) => (
            <ImageCard
              key={vi}
              variationIndex={vi}
              image={latest[vi]}
              onClick={() => onImageClick(vi)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
