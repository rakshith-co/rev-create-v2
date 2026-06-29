import React, { useState, useEffect } from "react";
import { listGeneratedCreatives, listAllCreatives, requestImageEdit, getJob, getImage, replaceCreativeImage } from "../api";
import { CreativeOut, JobOut, ImageStatus } from "../types";
import axios from "axios";

export default function StandaloneEdit({ provider }: { provider: "gemini" | "openai" }) {
  const [images, setImages] = useState<CreativeOut[]>([]);
  const [isLoadingImages, setIsLoadingImages] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [selectedImage, setSelectedImage] = useState<CreativeOut | null>(null);
  const [instruction, setInstruction] = useState("");
  const [refImages, setRefImages] = useState<File[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [error, setError] = useState("");
  const [resultJob, setResultJob] = useState<JobOut | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [searchId, setSearchId] = useState("");
  const [mode, setMode] = useState<"edit" | "replace">("edit");
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const [isReplacing, setIsReplacing] = useState(false);
  const [replaceSuccess, setReplaceSuccess] = useState(false);

  const PAGE_SIZE = 40;

  // Load images
  useEffect(() => {
    loadImages(1, true);
  }, []);

  async function loadImages(pageNum: number, reset: boolean = false) {
    setIsLoadingImages(true);
    try {
      const [generated, uploaded] = await Promise.all([
        listGeneratedCreatives(undefined, pageNum, PAGE_SIZE),
        listAllCreatives(undefined, undefined, pageNum, PAGE_SIZE),
      ]);
      const combined = [...generated, ...uploaded];
      const filtered = combined.filter(img =>
        (img.status === "done" || img.status === "uploaded") && img.creative_url
      );

      if (reset) {
        setImages(filtered);
      } else {
        setImages(prev => [...prev, ...filtered]);
      }

      setPage(pageNum);
      if (generated.length < PAGE_SIZE && uploaded.length < PAGE_SIZE) {
        setHasMore(false);
      } else {
        setHasMore(true);
      }
    } catch (e) {
      console.error("Failed to load images", e);
    } finally {
      setIsLoadingImages(false);
    }
  }

  const handleLoadMore = () => {
    if (!isLoadingImages && hasMore) {
      loadImages(page + 1);
    }
  };

  const handleRefresh = () => {
    loadImages(1, true);
  };

  const handleSearchById = async () => {
    const id = searchId.trim();
    if (!id) return;
    
    setIsLoadingImages(true);
    setError("");
    try {
      const img = await getImage(id);
      if (img.creative_url) {
        if (!images.find(i => i.id === img.id)) {
          setImages(prev => [img, ...prev]);
        }
        setSelectedImage(img);
        setSearchId("");
      } else {
        setError(`Image found (status: ${img.status}) but has no URL — it may still be processing or failed.`);
      }
    } catch (e) {
      setError("Image not found or error fetching it.");
      console.error("Search error", e);
    } finally {
      setIsLoadingImages(false);
    }
  };

  // Polling for job
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (jobId && isEditing) {
      interval = setInterval(async () => {
        try {
          const job = await getJob(jobId);
          setResultJob(job);
          if (["done", "failed", "partial_failure"].includes(job.status)) {
            setIsEditing(false);
            setJobId(null);
            clearInterval(interval);
            
            // If successful, update the base image to the new result
            if (job.status === "done" && job.creatives?.[0]) {
              setSelectedImage(job.creatives[0]);
              setInstruction("");
            }
          }
        } catch (e) {
          console.error("Polling error", e);
          setIsEditing(false);
          setJobId(null);
          clearInterval(interval);
          setError("Failed to poll job status.");
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [jobId, isEditing]);

  const handleEdit = async () => {
    if (!selectedImage || !instruction.trim() || isEditing) return;
    setIsEditing(true);
    setError("");
    setResultJob(null);
    setJobId(null);
    try {
      const accepted = await requestImageEdit(selectedImage.id, instruction.trim(), provider, refImages.length ? refImages : undefined);
      setJobId(accepted.job_id);
    } catch (e) {
      setIsEditing(false);
      const msg = axios.isAxiosError(e)
        ? (e.response?.data?.detail ?? e.message)
        : "Edit failed";
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
  };

  const handleReplace = async () => {
    if (!selectedImage || !replaceFile || isReplacing) return;
    setIsReplacing(true);
    setError("");
    setReplaceSuccess(false);
    try {
      const updated = await replaceCreativeImage(selectedImage.id, replaceFile);
      setSelectedImage(updated);
      setReplaceFile(null);
      setReplaceSuccess(true);
    } catch (e) {
      const msg = axios.isAxiosError(e)
        ? (e.response?.data?.detail ?? e.message)
        : "Replace failed";
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setIsReplacing(false);
    }
  };

  const handleReset = () => {
    setSelectedImage(null);
    setInstruction("");
    setRefImages([]);
    setResultJob(null);
    setJobId(null);
    setError("");
    setIsEditing(false);
    setReplaceFile(null);
    setReplaceSuccess(false);
  };

  const editedImage = resultJob?.creatives?.[0];

  return (
    <div className="max-w-6xl mx-auto space-y-8 pb-20">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Image Edit Test</h2>
        <button
          onClick={handleReset}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          Reset
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left: Selection (3 cols) */}
        <div className="lg:col-span-3 space-y-4">
          <p className="section-title">Select Image</p>
          
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
              disabled={isLoadingImages}
              className="px-3 py-2 bg-violet-600 text-white rounded-lg text-xs hover:bg-violet-500 disabled:opacity-50 transition"
            >
              Search
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2 overflow-y-auto max-h-[600px] pr-2 scrollbar-thin scrollbar-thumb-gray-800">
            {images.map((img) => (
              <button
                key={img.id}
                onClick={() => setSelectedImage(img)}
                className={`relative aspect-square rounded-lg border-2 overflow-hidden transition ${
                  selectedImage?.id === img.id ? "border-violet-500" : "border-gray-800 hover:border-gray-700"
                }`}
              >
                <img src={img.creative_url!} alt={img.name || "Image"} className="w-full h-full object-cover" />
                <div className="absolute inset-x-0 bottom-0 bg-black/60 py-1 px-1.5">
                  <p className="text-[10px] text-gray-300 truncate">{img.name || img.id.slice(0, 8)}</p>
                </div>
              </button>
            ))}
            
            {isLoadingImages && (
              <div className="col-span-2 py-4 flex justify-center">
                <div className="h-6 w-6 border-2 border-violet-500/20 border-t-violet-500 rounded-full animate-spin"></div>
              </div>
            )}

            {!isLoadingImages && images.length === 0 && (
              <p className="col-span-2 text-xs text-gray-600 text-center py-10">No images found</p>
            )}

            {!isLoadingImages && hasMore && images.length > 0 && (
              <button
                onClick={handleLoadMore}
                className="col-span-2 py-2 text-[10px] text-violet-400 hover:text-violet-300 transition"
              >
                Load More...
              </button>
            )}
          </div>
          <button 
            onClick={handleRefresh}
            disabled={isLoadingImages}
            className="w-full py-2 text-xs text-gray-400 hover:text-white transition bg-gray-900 rounded-lg disabled:opacity-50"
          >
            Refresh List
          </button>
        </div>

        {/* Middle: Workspace (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="section-card space-y-4">
            <p className="section-title">Original Image</p>
            {selectedImage ? (
              <div className="space-y-4">
                <div className="aspect-square bg-gray-900 rounded-xl overflow-hidden border border-gray-800">
                  <img src={selectedImage.creative_url!} alt="Selected" className="w-full h-full object-contain" />
                </div>
                <div className="bg-gray-800/50 rounded-lg p-3 text-xs text-gray-400 font-mono break-all">
                  ID: {selectedImage.id}
                </div>
              </div>
            ) : (
              <div className="aspect-square flex flex-col items-center justify-center border-2 border-dashed border-gray-800 rounded-2xl p-10 text-center">
                <p className="text-gray-500 text-sm">Select an image from the left to start</p>
              </div>
            )}
          </div>

          <div className="section-card space-y-4">
            <p className="section-title">Edit Instructions</p>
            <textarea
              className="input resize-none h-32"
              placeholder="Describe what to change (e.g., 'Make the background a vibrant sunset', 'Change the product color to blue')..."
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              disabled={!selectedImage || isEditing}
            />

            {/* Optional reference images */}
            <div className="space-y-2">
              <p className="text-xs text-gray-400">Reference Images <span className="text-gray-600">(optional — logo, product, etc.)</span></p>
              <label className={`flex items-center justify-center gap-2 w-full py-2 border border-dashed rounded-lg text-xs transition cursor-pointer ${
                isEditing || !selectedImage ? "opacity-40 pointer-events-none border-gray-800 text-gray-600" : "border-gray-700 text-gray-400 hover:border-violet-600 hover:text-violet-400"
              }`}>
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                Upload images
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  className="hidden"
                  disabled={isEditing || !selectedImage}
                  onChange={(e) => {
                    const files = Array.from(e.target.files || []);
                    setRefImages(prev => [...prev, ...files]);
                    e.target.value = "";
                  }}
                />
              </label>
              {refImages.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {refImages.map((f, i) => (
                    <div key={i} className="flex items-center gap-1.5 bg-gray-800 rounded-lg px-2 py-1">
                      <span className="text-[10px] text-gray-300 max-w-[100px] truncate">{f.name}</span>
                      <button
                        onClick={() => setRefImages(prev => prev.filter((_, j) => j !== i))}
                        className="text-gray-500 hover:text-red-400 transition"
                      >
                        <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <button
              onClick={handleEdit}
              disabled={!selectedImage || !instruction.trim() || isEditing}
              className="w-full py-4 rounded-xl font-bold text-white transition
                         bg-violet-600 hover:bg-violet-500 disabled:opacity-40"
            >
              {isEditing ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="h-4 w-4 border-2 border-white/20 border-t-white rounded-full animate-spin"></div>
                  Generating Edit...
                </span>
              ) : "Apply Edit via /api/images/{id}/edit"}
            </button>
          </div>

          {error && (
            <div className="p-4 bg-red-900/30 border border-red-800 rounded-xl text-sm text-red-300">
              {error}
            </div>
          )}
        </div>

        {/* Right: Results & Conversation (4 cols) */}
        <div className="lg:col-span-4 space-y-6">
          <div className="section-card h-full min-h-[400px] flex flex-col space-y-6">
            
            {/* Conversation Log */}
            {resultJob && (
              <div className="space-y-4">
                <p className="section-title text-violet-400">Gemini Conversation Log</p>
                <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-4 overflow-y-auto max-h-64 scrollbar-thin scrollbar-thumb-gray-700">
                  
                  {/* Turn 1: Context Brief */}
                  <div className="space-y-2 border-b border-gray-800 pb-4">
                    <p className="text-xs font-semibold text-gray-500 uppercase">System Context</p>
                    <div className="bg-blue-950/20 border border-blue-900/30 rounded px-3 py-2 text-xs text-blue-200 space-y-1">
                      <p><strong>System Prompt:</strong> You are an expert ad creative editor. You receive an ad creative image along with target audience and creative strategy context. Apply each edit instruction precisely while preserving brand identity, layout, colour palette, and creative direction. Only modify what the instruction explicitly requests — leave everything else unchanged.</p>
                      {/* We don't have persona_info/strategy on JobOut directly, but we can imply they were sent if the image had them */}
                      {selectedImage?.generated && (
                         <p className="text-gray-400 mt-2 italic">(Base image attached here)</p>
                      )}
                    </div>
                  </div>

                  {/* Past Instructions */}
                  {resultJob.edit_history && resultJob.edit_history.map((histInst, i) => (
                    <div key={i} className="space-y-3">
                      <div className="flex flex-col items-end">
                        <p className="text-[10px] text-gray-500 mb-1">User</p>
                        <div className="bg-violet-600 text-white rounded-xl rounded-tr-sm px-3 py-2 text-xs max-w-[85%]">
                          {histInst}
                        </div>
                      </div>
                      <div className="flex flex-col items-start">
                        <p className="text-[10px] text-gray-500 mb-1">Gemini</p>
                        <div className="bg-gray-800 text-gray-300 rounded-xl rounded-tl-sm px-3 py-2 text-xs max-w-[85%]">
                          Edit applied.
                        </div>
                      </div>
                    </div>
                  ))}

                  {/* Latest Instruction */}
                  <div className="space-y-3 pt-2">
                    <div className="flex flex-col items-end">
                      <p className="text-[10px] text-gray-500 mb-1">User</p>
                      <div className="bg-violet-600 text-white rounded-xl rounded-tr-sm px-3 py-2 text-xs max-w-[85%]">
                        {resultJob.edit_instruction}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div>
              <p className="section-title">Result Image</p>
              <div className="flex-1 flex flex-col mt-4">
                {!resultJob && !isEditing && (
                  <div className="flex-1 flex flex-col items-center justify-center text-center p-10 border-2 border-dashed border-gray-800 rounded-2xl">
                    <div className="bg-gray-900 p-4 rounded-full mb-4">
                      <svg className="h-8 w-8 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                      </svg>
                    </div>
                    <p className="text-gray-500 text-sm">Edited image will appear here</p>
                  </div>
                )}

                {isEditing && (
                  <div className="flex-1 flex flex-col items-center justify-center space-y-4 py-10 border-2 border-dashed border-gray-800 rounded-2xl">
                    <div className="relative">
                      <div className="h-12 w-12 border-4 border-violet-500/20 border-t-violet-500 rounded-full animate-spin"></div>
                    </div>
                    <p className="text-white font-medium italic">Gemini is editing...</p>
                  </div>
                )}

                {resultJob && resultJob.status === "done" && editedImage && (
                  <div className="space-y-4 animate-in fade-in duration-500">
                    <div className="aspect-square bg-gray-900 rounded-xl overflow-hidden border border-gray-800">
                      <img src={editedImage.creative_url!} alt="Result" className="w-full h-full object-contain" />
                    </div>
                    <div className="bg-green-950/20 border border-green-800/30 rounded-lg p-3">
                      <p className="text-xs text-green-400 font-medium flex items-center gap-2">
                        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                        Edit successful
                      </p>
                      <p className="text-[10px] text-gray-500 mt-1">New ID: {editedImage.id}</p>
                    </div>
                    {editedImage.creative_url && (
                      <a 
                        href={editedImage.creative_url} 
                        target="_blank" 
                        rel="noreferrer"
                        className="block text-center py-2 text-xs font-medium text-violet-400 hover:text-violet-300 transition border border-violet-800/30 rounded-lg"
                      >
                        Open Full Image
                      </a>
                    )}
                  </div>
                )}

                {resultJob && resultJob.status === "failed" && (
                  <div className="flex-1 flex flex-col items-center justify-center text-center p-10 border-2 border-dashed border-red-900/50 rounded-2xl">
                    <div className="bg-red-950/30 p-4 rounded-full mb-4">
                      <svg className="h-8 w-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                    </div>
                    <p className="text-red-400 font-medium">Generation Failed</p>
                    <p className="text-xs text-red-300/60 mt-2">{resultJob.creatives?.[0]?.error_message || "Unknown error"}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
