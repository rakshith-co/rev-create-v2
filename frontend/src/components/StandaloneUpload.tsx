import React, { useState } from "react";
import { uploadStaticCreatives } from "../api";
import { CreativeSubtype, ImageOut, UploadCreativeInputs } from "../types";
import { ImageUploadZone } from "./CreateProjectForm";
import axios from "axios";

const EMPTY_INPUTS: UploadCreativeInputs = {
  subtype: "feed-square",
  name: "",
  client_id: "revspot",
  campaign_tag: "",
  primary_text: "",
  headline: "",
  description: "",
  call_to_action: "Shop Now",
  files: [],
};

const SUBTYPES: { label: string; value: CreativeSubtype }[] = [
  { label: "Feed Square (1080x1080)", value: "feed-square" },
  { label: "Feed Landscape (1200x628)", value: "feed-landscape" },
  { label: "Story / Reels (1080x1920)", value: "story" },
  { label: "FB Banner (1200x444)", value: "fb-banner" },
];

export default function StandaloneUpload() {
  const [inputs, setInputs] = useState<UploadCreativeInputs>(EMPTY_INPUTS);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<ImageOut[]>([]);

  const handleUpload = async () => {
    if (isUploading) return;
    setIsUploading(true);
    setError("");
    setResults([]);
    try {
      const data = await uploadStaticCreatives(inputs);
      setResults(data);
    } catch (e) {
      const msg = axios.isAxiosError(e)
        ? (e.response?.data?.detail ?? e.message)
        : "Upload failed";
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setIsUploading(false);
    }
  };

  const updateField = (field: keyof UploadCreativeInputs, value: any) => {
    setInputs((prev) => ({ ...prev, [field]: value }));
  };

  const isValid = inputs.name.trim() && inputs.files.length > 0;

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-20">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Standalone Upload Test</h2>
        <button
          onClick={() => {
            setInputs(EMPTY_INPUTS);
            setResults([]);
            setError("");
          }}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          Reset Form
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left: Inputs */}
        <div className="space-y-6">
          <div className="section-card space-y-4">
            <p className="section-title">Core Details</p>
            <div>
              <label className="label">Creative Name *</label>
              <input
                className="input"
                placeholder="e.g. Summer Sale V1"
                value={inputs.name}
                onChange={(e) => updateField("name", e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">Subtype</label>
                <select
                  className="input"
                  value={inputs.subtype}
                  onChange={(e) => updateField("subtype", e.target.value)}
                >
                  {SUBTYPES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">Campaign Tag</label>
                <input
                  className="input"
                  placeholder="e.g. summer-2024"
                  value={inputs.campaign_tag}
                  onChange={(e) => updateField("campaign_tag", e.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="section-card space-y-4">
            <p className="section-title">Meta Ad Copy (Optional)</p>
            <div>
              <label className="label">Primary Text</label>
              <textarea
                className="input resize-none"
                rows={3}
                placeholder="The main text above the creative..."
                value={inputs.primary_text}
                onChange={(e) => updateField("primary_text", e.target.value)}
              />
            </div>
            <div>
              <label className="label">Headline</label>
              <input
                className="input"
                placeholder="Bold text next to CTA..."
                value={inputs.headline}
                onChange={(e) => updateField("headline", e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">Description</label>
                <input
                  className="input"
                  placeholder="Small text under headline..."
                  value={inputs.description}
                  onChange={(e) => updateField("description", e.target.value)}
                />
              </div>
              <div>
                <label className="label">CTA Button</label>
                <select
                  className="input"
                  value={inputs.call_to_action}
                  onChange={(e) => updateField("call_to_action", e.target.value)}
                >
                  <option value="Shop Now">Shop Now</option>
                  <option value="Learn More">Learn More</option>
                  <option value="Book Now">Book Now</option>
                  <option value="Sign Up">Sign Up</option>
                  <option value="Get Offer">Get Offer</option>
                </select>
              </div>
            </div>
          </div>

          <div className="section-card space-y-4">
            <p className="section-title">Creative Files</p>
            <ImageUploadZone
              images={inputs.files}
              onAdd={(files) => updateField("files", [...inputs.files, ...files])}
              onRemove={(i) => updateField("files", inputs.files.filter((_, idx) => idx !== i))}
            />
          </div>

          <button
            onClick={handleUpload}
            disabled={!isValid || isUploading}
            className="w-full py-4 rounded-xl font-bold text-white transition
                       bg-violet-600 hover:bg-violet-500 disabled:opacity-40"
          >
            {isUploading ? "Uploading..." : "Upload Static Creatives"}
          </button>

          {error && (
            <div className="p-4 bg-red-900/30 border border-red-800 rounded-xl text-sm text-red-300">
              {error}
            </div>
          )}
        </div>

        {/* Right: Results */}
        <div className="space-y-6">
          {results.length === 0 && !isUploading && (
            <div className="h-full flex flex-col items-center justify-center border-2 border-dashed border-gray-800 rounded-2xl p-10 text-center">
              <div className="bg-gray-900 p-4 rounded-full mb-4">
                <svg className="h-8 w-8 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </div>
              <p className="text-gray-500 text-sm">Uploaded creatives will appear here</p>
            </div>
          )}

          {isUploading && (
            <div className="h-full flex flex-col items-center justify-center space-y-4 bg-gray-900/50 rounded-2xl p-10">
              <div className="h-12 w-12 border-4 border-violet-500/20 border-t-violet-500 rounded-full animate-spin"></div>
              <p className="text-white font-medium">Uploading Files...</p>
            </div>
          )}

          {results.length > 0 && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="section-card bg-green-950/10 border-green-800/30">
                <p className="text-green-400 font-bold text-sm flex items-center gap-2">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Successfully uploaded {results.length} creatives
                </p>
              </div>

              {results[0].ad_copy?.platforms?.meta && (() => {
                const meta = results[0].ad_copy!.platforms!.meta!;
                const toArr = (v: string | string[]) => Array.isArray(v) ? v : [v];
                const primaryTexts = toArr(meta.primary_text);
                const headlines = toArr(meta.headline);
                const descriptions = toArr(meta.description);
                return (
                  <div className="section-card space-y-4 bg-violet-950/10 border-violet-800/30">
                    <p className="section-title text-violet-300">Attached Meta Ad Copy</p>
                    <div className="space-y-4">
                      <div>
                        <p className="text-[10px] font-bold text-violet-500 uppercase tracking-widest mb-2">Primary Text</p>
                        <div className="space-y-2">
                          {primaryTexts.map((text, idx) => (
                            <div key={idx} className="flex gap-2">
                              <span className="text-[9px] font-bold text-violet-400/50 mt-0.5 shrink-0">V{idx + 1}</span>
                              <p className="text-gray-300 text-xs leading-relaxed whitespace-pre-wrap flex-1">{text}</p>
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
                              <p className="text-white text-xs font-bold flex-1">{text}</p>
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
                              <p className="text-gray-400 text-[11px] flex-1">{text}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="pt-2 border-t border-violet-800/20">
                        <p className="text-[10px] font-bold text-violet-500 uppercase tracking-widest mb-1">Call to Action</p>
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-violet-600/30 text-violet-200 border border-violet-500/30">
                          {meta.call_to_action}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })()}

              <div className="grid grid-cols-2 gap-4">
                {results.map((img) => (
                  <div key={img.id} className="group relative aspect-square bg-gray-900 rounded-xl overflow-hidden border border-gray-800">
                    {img.creative_url ? (
                      <img
                        src={img.creative_url}
                        alt="Uploaded"
                        className="w-full h-full object-cover transition duration-500 group-hover:scale-110"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-xs text-gray-600">No URL</div>
                    )}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity p-3 flex flex-col justify-end">
                      <p className="text-[10px] text-gray-300 font-mono truncate">{img.name}</p>
                      <p className="text-[9px] text-gray-500 uppercase mt-0.5">{img.metadata.subtype}</p>
                      {img.creative_url && (
                        <a
                          href={img.creative_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-1.5 self-start text-[10px] font-semibold text-white bg-white/20 hover:bg-white/30 px-2 py-0.5 rounded"
                          onClick={(e) => e.stopPropagation()}
                        >
                          View Full
                        </a>
                      )}
                    </div>
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
