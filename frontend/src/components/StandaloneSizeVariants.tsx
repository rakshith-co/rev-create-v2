import React, { useState, useEffect } from "react";
import JSZip from "jszip";
import { listGeneratedCreatives, requestSizeVariants, getJob, getImage } from "../api";
import { CreativeOut, ImageOut, PLATFORM_SIZES, JobOut } from "../types";
import StatusBadge from "./StatusBadge";

const StandaloneSizeVariants: React.FC<{ provider: "gemini" | "openai" }> = ({ provider }) => {
  const [creatives, setCreatives] = useState<CreativeOut[]>([]);
  const [selectedCreativeId, setSelectedCreativeId] = useState<string>("");
  const [platform, setPlatform] = useState<string>("meta");
  const [selectedSizes, setSelectedSizes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetchingCreatives, setFetchingCreatives] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobResult, setJobResult] = useState<JobOut | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [searchId, setSearchId] = useState("");
  const [isDownloading, setIsDownloading] = useState(false);

  useEffect(() => {
    setFetchingCreatives(true);
    listGeneratedCreatives(undefined, 1, 1000)
      .then((data) => {
        // Filter for done creatives only as they are suitable for size variants
        setCreatives(data.filter(c => c.status === "done"));
      })
      .catch((err) => {
        console.error("Failed to fetch creatives", err);
        setError("Failed to load creatives list.");
      })
      .finally(() => setFetchingCreatives(false));
  }, []);

  // Update selected sizes when platform changes to include all by default
  useEffect(() => {
    setSelectedSizes(PLATFORM_SIZES[platform].sizes.map(s => s.dimensions));
  }, [platform]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (jobId && loading) {
      interval = setInterval(async () => {
        try {
          const job = await getJob(jobId);
          setJobResult(job);
          if (["done", "failed", "partial_failure"].includes(job.status)) {
            setLoading(false);
            setJobId(null);
            clearInterval(interval);
          }
        } catch (e) {
          console.error("Polling error", e);
          setLoading(false);
          setJobId(null);
          clearInterval(interval);
          setError("Failed to poll job status.");
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [jobId, loading]);

  const handleToggleSize = (dim: string) => {
    setSelectedSizes((prev) =>
      prev.includes(dim) ? prev.filter((d) => d !== dim) : [...prev, dim]
    );
  };

  const handleSearchById = async () => {
    const id = searchId.trim();
    if (!id) return;
    
    setFetchingCreatives(true);
    setError(null);
    try {
      const img = await getImage(id);
      if (img.creative_url) {
        if (!creatives.find(c => c.id === img.id)) {
          setCreatives(prev => [img, ...prev]);
        }
        setSelectedCreativeId(img.id);
        setSearchId("");
      } else {
        setError(`Image found (status: ${img.status}) but has no URL — it may still be processing or failed.`);
      }
    } catch (e) {
      setError("Image not found or error fetching it.");
      console.error("Search error", e);
    } finally {
      setFetchingCreatives(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedCreativeId) return;
    setLoading(true);
    setError(null);
    setJobResult(null);
    setJobId(null);

    try {
      // The API takes (path_param_id, platform, body_creative_id, sizes)
      // We pass selectedCreativeId as both for safety/simplicity
      const accepted = await requestSizeVariants(
        selectedCreativeId,
        platform,
        selectedCreativeId,
        selectedSizes,
        provider
      );
      setJobId(accepted.job_id);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to generate size variants.");
      setLoading(false);
    }
  };

  const handleDownloadAll = async () => {
    if (!jobResult || jobResult.creatives.length === 0) return;
    setIsDownloading(true);
    try {
      const zip = new JSZip();
      const apiBase = (import.meta.env.VITE_API_URL || "") + "/api";
      
      const doneCreatives = jobResult.creatives.filter(c => c.status === "done");
      
      await Promise.all(
        doneCreatives.map(async (c) => {
          const blob = await fetch(`${apiBase}/images/${c.id}/download`).then((r) => r.blob());
          const name = (c.metadata?.size_label || "variant").replace(/ \/ /g, "-").replace(/ /g, "_");
          zip.file(`${name}.png`, blob);
        })
      );

      const zipBlob = await zip.generateAsync({ type: "blob" });
      const objectUrl = URL.createObjectURL(zipBlob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = `size_variants_${platform}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
    } catch (e) {
      console.error("Download failed", e);
      setError("Failed to download images.");
    } finally {
      setIsDownloading(false);
    }
  };

  const selectedCreative = creatives.find(c => c.id === selectedCreativeId);

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-20">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Size Variants Test</h2>
        <button
          onClick={() => {
            setSelectedCreativeId("");
            setJobResult(null);
            setError(null);
            setLoading(false);
            setJobId(null);
            setSearchId("");
          }}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          Reset
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="space-y-6">
          <div className="section-card space-y-4">
            <p className="section-title">Select Source Creative</p>
            
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Search by ID..."
                className="input text-xs py-2 px-3 flex-1"
                value={searchId}
                onChange={(e) => setSearchId(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearchById()}
              />
              <button
                onClick={handleSearchById}
                disabled={fetchingCreatives}
                className="px-3 py-2 bg-violet-600 text-white rounded-lg text-xs hover:bg-violet-500 disabled:opacity-50 transition"
              >
                Search
              </button>
            </div>

            <div className="relative">
              <label className="label">Creative *</label>
              <select
                className="input"
                value={selectedCreativeId}
                onChange={(e) => setSelectedCreativeId(e.target.value)}
                disabled={fetchingCreatives}
              >
                <option value="">-- Select a completed creative --</option>
                {creatives.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name || c.id.substring(0, 8)} ({c.metadata.subtype})
                  </option>
                ))}
              </select>
              {fetchingCreatives && <div className="absolute right-10 top-9"><div className="h-4 w-4 border-2 border-violet-500/20 border-t-violet-500 rounded-full animate-spin"></div></div>}
            </div>

            {selectedCreative && (
              <div className="mt-4 p-4 bg-gray-900 rounded-xl border border-gray-800 flex flex-col gap-4">
                <div className="aspect-square w-full relative bg-gray-950 rounded-lg overflow-hidden border border-gray-800">
                  {selectedCreative.creative_url ? (
                    <img
                      src={selectedCreative.creative_url}
                      alt="Source"
                      className="w-full h-full object-contain"
                    />
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-700">No Image</div>
                  )}
                </div>
                <div className="text-xs space-y-1.5">
                  <p className="text-gray-200 font-bold text-sm">{selectedCreative.name || "Unnamed Creative"}</p>
                  <p className="text-violet-400 uppercase font-semibold tracking-wider">{selectedCreative.metadata.subtype}</p>
                  <p className="text-gray-500 font-mono break-all bg-gray-950 p-2 rounded mt-2">ID: {selectedCreative.id}</p>
                </div>
              </div>
            )}
          </div>

          <div className="section-card space-y-4">
            <p className="section-title">Target Configuration</p>
            <div>
              <label className="label">Platform</label>
              <div className="flex gap-2">
                {Object.keys(PLATFORM_SIZES).map((p) => (
                  <button
                    key={p}
                    onClick={() => setPlatform(p)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                      platform === p
                        ? "bg-violet-600 text-white"
                        : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                    }`}
                  >
                    {PLATFORM_SIZES[p].label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="label">Select Sizes</label>
              <div className="grid grid-cols-1 gap-2">
                {PLATFORM_SIZES[platform].sizes.map((s) => (
                  <label
                    key={s.dimensions}
                    className={`flex items-center justify-between p-3 rounded-lg border transition cursor-pointer ${
                      selectedSizes.includes(s.dimensions)
                        ? "bg-violet-900/20 border-violet-500/50"
                        : "bg-gray-900 border-gray-800 hover:border-gray-700"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        className="rounded border-gray-700 text-violet-600 focus:ring-violet-500 bg-gray-800"
                        checked={selectedSizes.includes(s.dimensions)}
                        onChange={() => handleToggleSize(s.dimensions)}
                      />
                      <div>
                        <p className="text-sm font-medium text-white">{s.label}</p>
                        <p className="text-xs text-gray-500">{s.dimensions}</p>
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={!selectedCreativeId || selectedSizes.length === 0 || loading}
            className="w-full py-4 rounded-xl font-bold text-white transition bg-violet-600 hover:bg-violet-500 disabled:opacity-40"
          >
            {loading && !jobResult ? (
              <span className="flex items-center justify-center gap-2">
                <div className="h-4 w-4 border-2 border-white/20 border-t-white rounded-full animate-spin"></div>
                Starting Generation...
              </span>
            ) : loading ? (
              <span className="flex items-center justify-center gap-2">
                <div className="h-4 w-4 border-2 border-white/20 border-t-white rounded-full animate-spin"></div>
                Generating Variants...
              </span>
            ) : "Generate Selected Sizes"}
          </button>

          {error && (
            <div className="p-4 bg-red-900/30 border border-red-800 rounded-xl text-sm text-red-300">
              {error}
            </div>
          )}
        </div>

        <div className="space-y-6">
          {!jobResult && !loading && (
            <div className="h-full flex flex-col items-center justify-center border-2 border-dashed border-gray-800 rounded-2xl p-10 text-center">
              <div className="bg-gray-900 p-4 rounded-full mb-4">
                <svg className="h-8 w-8 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </div>
              <p className="text-gray-500 text-sm">Results will appear here</p>
            </div>
          )}

          {loading && !jobResult && (
            <div className="h-full flex flex-col items-center justify-center space-y-4 bg-gray-900/50 rounded-2xl p-10">
              <div className="h-12 w-12 border-4 border-violet-500/20 border-t-violet-500 rounded-full animate-spin" />
              <p className="text-white font-medium">Requesting Size Variants...</p>
            </div>
          )}

          {jobResult && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="flex items-center justify-between">
                <p className="section-title">Results ({jobResult.creatives.length})</p>
                <button
                  onClick={handleDownloadAll}
                  disabled={isDownloading || jobResult.creatives.every(c => c.status !== "done")}
                  className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg text-xs font-semibold border border-gray-700 transition disabled:opacity-40"
                >
                  {isDownloading ? "Zipping..." : "Download All (.zip)"}
                </button>
              </div>
              <div className="grid grid-cols-2 gap-4">
                {jobResult.creatives.map((img) => (
                  <div key={img.id} className="group relative aspect-square bg-gray-900 rounded-xl overflow-hidden border border-gray-800">
                    {img.status === "done" || img.status === "uploaded" && img.creative_url ? (
                      <img
                        src={img.creative_url!}
                        alt="Variant"
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center p-4">
                         <StatusBadge status={img.status as any} />
                         {img.error_message && <p className="text-[10px] text-red-400 mt-2 text-center line-clamp-2">{img.error_message}</p>}
                      </div>
                    )}
                    <div className="absolute top-2 left-2">
                       <StatusBadge status={img.status as any} />
                    </div>
                    {img.status === "done" && img.creative_url && (
                      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity p-3 flex flex-col justify-end">
                        <p className="text-[10px] text-gray-300 font-mono truncate">{img.metadata?.size_label}</p>
                        {img.metadata?.size_specs && <p className="text-[9px] text-gray-500">{img.metadata.size_specs.width}x{img.metadata.size_specs.height}</p>}
                        <a
                          href={img.creative_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-1.5 self-start text-[10px] font-semibold text-white bg-white/20 hover:bg-white/30 px-2 py-0.5 rounded"
                          onClick={(e) => e.stopPropagation()}
                        >
                          View Full
                        </a>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StandaloneSizeVariants;
