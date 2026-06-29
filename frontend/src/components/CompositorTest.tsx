import React, { useRef, useState } from "react";

const API = "/api/compositor/test";

export default function CompositorTest() {
  const [image, setImage] = useState<File | null>(null);
  const [qrCode, setQrCode] = useState<File | null>(null);
  const [rera, setRera] = useState("");
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const imageInputRef = useRef<HTMLInputElement>(null);
  const qrInputRef = useRef<HTMLInputElement>(null);

  const imagePreview = image ? URL.createObjectURL(image) : null;

  async function handleRun() {
    if (!image) return;
    setLoading(true);
    setError(null);
    setResultUrl(null);

    const fd = new FormData();
    fd.append("image", image);
    if (rera.trim()) fd.append("rera_number", rera.trim());
    if (qrCode) fd.append("qr_code", qrCode);

    try {
      const res = await fetch(API, { method: "POST", body: fd });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text);
      }
      const blob = await res.blob();
      setResultUrl(URL.createObjectURL(blob));
    } catch (e: any) {
      setError(e.message ?? "Request failed");
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setImage(null);
    setQrCode(null);
    setRera("");
    setResultUrl(null);
    setError(null);
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h2 className="text-lg font-semibold text-white">Compositor Test</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Controls */}
        <div className="space-y-4">
          {/* Image upload */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Source Image *</label>
            <div
              onClick={() => imageInputRef.current?.click()}
              className="cursor-pointer border-2 border-dashed border-gray-700 rounded-lg p-4 flex flex-col items-center justify-center gap-2 hover:border-gray-500 transition min-h-[120px]"
            >
              {imagePreview ? (
                <img src={imagePreview} className="max-h-32 rounded object-contain" />
              ) : (
                <span className="text-xs text-gray-500">Click to upload image</span>
              )}
            </div>
            <input
              ref={imageInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => {
                setImage(e.target.files?.[0] ?? null);
                setResultUrl(null);
              }}
            />
          </div>

          {/* RERA number */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">RERA Number</label>
            <input
              type="text"
              value={rera}
              onChange={(e) => setRera(e.target.value)}
              placeholder="e.g. P51800012345"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-violet-500"
            />
          </div>

          {/* QR upload */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">QR Code (optional)</label>
            <div
              onClick={() => qrInputRef.current?.click()}
              className="cursor-pointer border-2 border-dashed border-gray-700 rounded-lg p-3 flex items-center gap-3 hover:border-gray-500 transition"
            >
              {qrCode ? (
                <>
                  <img src={URL.createObjectURL(qrCode)} className="h-12 w-12 object-contain rounded" />
                  <span className="text-xs text-gray-400 truncate">{qrCode.name}</span>
                </>
              ) : (
                <span className="text-xs text-gray-500">Click to upload QR code</span>
              )}
            </div>
            <input
              ref={qrInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => setQrCode(e.target.files?.[0] ?? null)}
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <button
              onClick={handleRun}
              disabled={!image || loading}
              className="flex-1 px-4 py-2 rounded-lg text-sm font-medium bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white transition"
            >
              {loading ? "Processing…" : "Run Compositor"}
            </button>
            <button
              onClick={handleReset}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-gray-800 hover:bg-gray-700 text-gray-300 transition"
            >
              Reset
            </button>
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-950 border border-red-800 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>

        {/* Result */}
        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium text-gray-400">Result</label>
          <div className="flex-1 border border-gray-800 rounded-lg overflow-hidden bg-gray-900 flex items-center justify-center min-h-[300px]">
            {resultUrl ? (
              <img src={resultUrl} className="max-w-full max-h-[600px] object-contain" />
            ) : (
              <span className="text-xs text-gray-600">Output will appear here</span>
            )}
          </div>
          {resultUrl && (
            <a
              href={resultUrl}
              download="compositor_result.jpg"
              className="text-center px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-800 hover:bg-gray-700 text-gray-300 transition"
            >
              Download
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
