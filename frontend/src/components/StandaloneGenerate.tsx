import React, { useState, useEffect } from "react";
import { standaloneGenerate, getJob } from "../api";
import { JobOut, StandaloneGenerateInputs } from "../types";
import { ImageUploadZone } from "./CreateProjectForm";
import axios from "axios";

const EMPTY_INPUTS: StandaloneGenerateInputs = {
  product_name: "",
  description: "",
  ad_format: "1080x1080",
  count: 4,
  product_images: [],
  ref_images: [],
  logo_images: [],
  qr_code: null,
  enable_rera: false,
  rera_number: "",
  persona_info: "",
  creative_strategy: "",
  instructions: "",
};

export default function StandaloneGenerate({ provider }: { provider: "gemini" | "openai" }) {
  const [inputs, setInputs] = useState<StandaloneGenerateInputs>(EMPTY_INPUTS);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<JobOut | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (jobId && isGenerating) {
      interval = setInterval(async () => {
        try {
          const job = await getJob(jobId);
          setResult(job);
          if (["done", "failed", "partial_failure"].includes(job.status)) {
            setIsGenerating(false);
            setJobId(null);
            clearInterval(interval);
          }
        } catch (e) {
          console.error("Polling error", e);
          setIsGenerating(false);
          setJobId(null);
          clearInterval(interval);
          setError("Failed to poll job status.");
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [jobId, isGenerating]);

  const handleGenerate = async () => {
    if (isGenerating) return;
    setIsGenerating(true);
    setError("");
    setResult(null);
    setJobId(null);
    try {
      const accepted = await standaloneGenerate({ ...inputs, provider });
      setJobId(accepted.job_id);
    } catch (e) {
      setIsGenerating(false);
      const msg = axios.isAxiosError(e)
        ? (e.response?.data?.detail ?? e.message)
        : "Generation failed";
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
  };

  const updateField = (field: keyof StandaloneGenerateInputs, value: any) => {
    setInputs((prev) => ({ ...prev, [field]: value }));
  };

  const isValid = inputs.product_name.trim();

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-20">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Standalone API Test</h2>
        <div className="flex items-center gap-4">
          <button
            onClick={() => {
              setInputs(EMPTY_INPUTS);
              setResult(null);
              setError("");
              setIsGenerating(false);
              setJobId(null);
            }}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            Reset Form
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left: Inputs */}
        <div className="space-y-6">
          <div className="section-card space-y-4">
            <p className="section-title">Core Details</p>
            <div>
              <label className="label">Product Name *</label>
              <input
                className="input"
                value={inputs.product_name}
                onChange={(e) => updateField("product_name", e.target.value)}
              />
            </div>
            <div>
              <label className="label">Description</label>
              <textarea
                className="input resize-none"
                rows={3}
                value={inputs.description}
                onChange={(e) => updateField("description", e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">Format</label>
                <select
                  className="input"
                  value={inputs.ad_format}
                  onChange={(e) => updateField("ad_format", e.target.value)}
                >
                  <option value="1080x1080">1080x1080 (Square)</option>
                  <option value="1200x628">1200x628 (Landscape)</option>
                  <option value="1080x1920">1080x1920 (Portrait)</option>
                </select>
              </div>
              <div>
                <label className="label">Count</label>
                <select
                  className="input"
                  value={inputs.count}
                  onChange={(e) => updateField("count", parseInt(e.target.value))}
                >
                  <option value={1}>1 Image</option>
                  <option value={4}>4 Images</option>
                </select>
              </div>
            </div>
          </div>

          <div className="section-card space-y-4">
            <p className="section-title">Advanced</p>
            <div>
              <label className="label">Persona Info</label>
              <input
                className="input"
                placeholder="e.g. Urban millennials interested in fitness"
                value={inputs.persona_info}
                onChange={(e) => updateField("persona_info", e.target.value)}
              />
            </div>
            <div>
              <label className="label">Creative Strategy</label>
              <textarea
                className="input resize-none"
                rows={2}
                placeholder="e.g. Focus on speed and comfort"
                value={inputs.creative_strategy}
                onChange={(e) => updateField("creative_strategy", e.target.value)}
              />
            </div>
            <div>
              <label className="label">Additional Instructions</label>
              <textarea
                className="input resize-none"
                rows={2}
                placeholder="e.g. Use warm tones, include a sense of urgency, avoid blue colours"
                value={inputs.instructions}
                onChange={(e) => updateField("instructions", e.target.value)}
              />
            </div>
          </div>

          <div className="section-card space-y-4">
            <p className="section-title">Images</p>
            <div>
              <label className="label">Product Images</label>
              <ImageUploadZone
                images={inputs.product_images}
                onAdd={(files) => updateField("product_images", [...inputs.product_images, ...files])}
                onRemove={(i) => updateField("product_images", inputs.product_images.filter((_, idx) => idx !== i))}
              />
            </div>
            <div>
              <label className="label">Reference Ads</label>
              <ImageUploadZone
                images={inputs.ref_images}
                onAdd={(files) => updateField("ref_images", [...inputs.ref_images, ...files])}
                onRemove={(i) => updateField("ref_images", inputs.ref_images.filter((_, idx) => idx !== i))}
              />
            </div>
            <div>
              <label className="label">Logo Image</label>
              <ImageUploadZone
                images={inputs.logo_images}
                onAdd={(files) => updateField("logo_images", [...inputs.logo_images, ...files])}
                onRemove={(i) => updateField("logo_images", inputs.logo_images.filter((_, idx) => idx !== i))}
              />
            </div>
          </div>

          <div className="section-card space-y-4">
            <p className="section-title">RERA Compliance</p>

            <div>
              <label className="label">RERA Number <span className="text-gray-500 font-normal">(optional)</span></label>
              <input
                type="text"
                className="input w-full"
                placeholder="e.g. P02400006099"
                value={inputs.rera_number ?? ""}
                onChange={(e) => updateField("rera_number", e.target.value)}
              />
            </div>

            <div>
              <label className="label">QR Code Image <span className="text-gray-500 font-normal">(optional)</span></label>
              <ImageUploadZone
                images={inputs.qr_code ? [inputs.qr_code] : []}
                onAdd={(files) => updateField("qr_code", files[0])}
                onRemove={() => updateField("qr_code", null)}
              />
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={!isValid || isGenerating}
            className={`w-full py-4 rounded-xl font-bold text-white transition disabled:opacity-40 ${
              provider === "openai"
                ? "bg-emerald-600 hover:bg-emerald-500"
                : "bg-violet-600 hover:bg-violet-500"
            }`}
          >
            {isGenerating
              ? "Generating..."
              : "Generate"}
          </button>

          {error && (
            <div className="p-4 bg-red-900/30 border border-red-800 rounded-xl text-sm text-red-300">
              {error}
            </div>
          )}
        </div>

        {/* Right: Results */}
        <div className="space-y-6">
          {!result && !isGenerating && (
            <div className="h-full flex flex-col items-center justify-center border-2 border-dashed border-gray-800 rounded-2xl p-10 text-center">
              <div className="bg-gray-900 p-4 rounded-full mb-4">
                <svg className="h-8 w-8 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </div>
              <p className="text-gray-500 text-sm">Results will appear here after generation</p>
            </div>
          )}

          {isGenerating && !result?.headline && (
            <div className="h-full flex flex-col items-center justify-center space-y-4 bg-gray-900/50 rounded-2xl p-10">
              <div className="relative">
                <div className="h-12 w-12 border-4 border-violet-500/20 border-t-violet-500 rounded-full animate-spin"></div>
              </div>
              <div className="text-center">
                <p className="text-white font-medium">Processing Pipeline</p>
                <p className="text-gray-500 text-xs mt-1">
                  {result?.status === "pending" || !result
                    ? "Uploading images to S3..."
                    : result?.status === "generating_copy" 
                    ? "Writing copy & image prompts (~15s)..."
                    : "Generating Copy..."}
                </p>
              </div>
            </div>
          )}

          {result && result.headline && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="section-card space-y-4 relative">
                {isGenerating && <div className="absolute top-4 right-4 h-4 w-4 border-2 border-violet-500/20 border-t-violet-500 rounded-full animate-spin"></div>}
                <p className="section-title text-violet-400">Generated Copy (In-Image)</p>
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Headline</p>
                  <p className="text-lg text-white font-bold leading-tight">{result.headline}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Body Copy</p>
                  <p className="text-gray-300 text-sm">{result.body_copy}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">CTA</p>
                  <p className="inline-block px-4 py-1.5 bg-violet-600 rounded text-xs font-bold text-white uppercase">{result.generated_cta}</p>
                </div>
              </div>

              {result.ad_copy?.platforms?.meta && (() => {
                const meta = result.ad_copy!.platforms!.meta!;
                const toArr = (v: string | string[]) => Array.isArray(v) ? v : [v];
                const primaryTexts = toArr(meta.primary_text);
                const headlines = toArr(meta.headline);
                const descriptions = toArr(meta.description);
                return (
                  <div className="section-card space-y-4 bg-violet-950/10 border-violet-800/30">
                    <p className="section-title text-violet-300">Meta Ad Platform Copy</p>
                    <div className="space-y-4">
                      <div>
                        <p className="text-[10px] font-bold text-violet-500 uppercase tracking-widest mb-2">Primary Text</p>
                        <div className="space-y-2">
                          {primaryTexts.map((text, idx) => (
                            <div key={idx} className="flex gap-2">
                              <span className="text-[9px] font-bold text-violet-400/50 mt-0.5 shrink-0">V{idx + 1}</span>
                              <p className="text-gray-300 text-sm leading-relaxed whitespace-pre-wrap flex-1">{text}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="pt-2 border-t border-violet-800/20">
                        <p className="text-[10px] font-bold text-violet-500 uppercase tracking-widest mb-2">Headline</p>
                        <div className="space-y-1.5">
                          {headlines.map((text, idx) => (
                            <div key={idx} className="flex gap-2 items-baseline">
                              <span className="text-[9px] font-bold text-violet-400/50 shrink-0">V{idx + 1}</span>
                              <p className="text-white text-sm font-bold flex-1">{text}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="pt-2 border-t border-violet-800/20">
                        <p className="text-[10px] font-bold text-violet-500 uppercase tracking-widest mb-2">Description</p>
                        <div className="space-y-1.5">
                          {descriptions.map((text, idx) => (
                            <div key={idx} className="flex gap-2 items-baseline">
                              <span className="text-[9px] font-bold text-violet-400/50 shrink-0">V{idx + 1}</span>
                              <p className="text-gray-400 text-xs flex-1">{text}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="pt-2 border-t border-violet-800/20">
                        <p className="text-[10px] font-bold text-violet-500 uppercase tracking-widest mb-1">Call to Action</p>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-violet-900/40 text-violet-200 border border-violet-700/50">
                          {meta.call_to_action}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {result.image_prompt && (
                <div className="section-card space-y-4">
                  <p className="section-title text-violet-400">Image Prompt</p>
                  <div className="p-3 bg-black/40 rounded-lg border border-gray-800">
                    <p className="text-xs text-gray-400 font-mono leading-relaxed">{result.image_prompt}</p>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                {result.creatives.map((img) => (
                  <div key={img.id} className="group relative aspect-square bg-gray-900 rounded-xl overflow-hidden border border-gray-800">
                    {img.status === "done" && img.creative_url ? (
                      <img
                        src={img.creative_url}
                        alt="Generated"
                        className="w-full h-full object-cover transition duration-500 group-hover:scale-110"
                      />
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center space-y-2">
                         {["pending", "generating", "retrying"].includes(img.status) && (
                           <div className="h-4 w-4 border-2 border-gray-500 border-t-white rounded-full animate-spin"></div>
                         )}
                         <span className="text-xs text-gray-500 capitalize">{img.status}</span>
                      </div>
                    )}
                    {img.status === "done" && img.creative_url && (
                      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity p-3 flex flex-col justify-end">
                        <p className="text-[10px] text-gray-300 font-mono truncate">{img.s3_key}</p>
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
}
