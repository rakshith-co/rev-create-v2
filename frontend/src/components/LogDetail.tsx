import React, { useState } from "react";
import { EvalCriterion, LogOut } from "../types";
import { updateLogEval } from "../api";

interface Props {
  log: LogOut;
  onClose: () => void;
  onSaved: (updated: LogOut) => void;
}

function Section({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-gray-800 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-900 hover:bg-gray-800 transition text-left"
      >
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{title}</span>
        <svg
          className={`h-3.5 w-3.5 text-gray-500 transition-transform ${open ? "rotate-180" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      {open && <div className="px-4 py-3 bg-gray-950 text-sm text-gray-300 space-y-1">{children}</div>}
    </div>
  );
}

function KV({ label, value }: { label: string; value: string | boolean }) {
  if (!value && value !== false) return null;
  return (
    <div className="flex gap-2">
      <span className="text-gray-500 w-36 flex-shrink-0">{label}</span>
      <span className="text-gray-200 break-words">{String(value)}</span>
    </div>
  );
}

function Mono({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div>
      <p className="text-gray-500 text-xs mb-1">{label}</p>
      <pre className="bg-gray-900 rounded p-3 text-xs text-gray-300 whitespace-pre-wrap break-words font-mono max-h-48 overflow-y-auto">
        {value}
      </pre>
    </div>
  );
}

export default function LogDetail({ log, onClose, onSaved }: Props) {
  const [criteria, setCriteria] = useState<EvalCriterion[]>(
    log.eval.criteria.map((c) => ({ ...c }))
  );
  const [overallNotes, setOverallNotes] = useState(log.eval.overall_notes);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [expandedImage, setExpandedImage] = useState<string | null>(null);

  const handleScoreChange = (idx: number, val: string) => {
    const num = val === "" ? null : Math.min(10, Math.max(1, Number(val)));
    setCriteria((prev) => prev.map((c, i) => (i === idx ? { ...c, score: num } : c)));
  };

  const handleNotesChange = (idx: number, val: string) => {
    setCriteria((prev) => prev.map((c, i) => (i === idx ? { ...c, notes: val } : c)));
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveError("");
    try {
      const updated = await updateLogEval(log.id, { criteria, overall_notes: overallNotes });
      onSaved(updated);
    } catch {
      setSaveError("Failed to save scores. Please try again.");
    } finally {
      setIsSaving(false);
    }
  };

  const doneImages = log.images.filter((img) => img.status === "done");

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Panel */}
      <div className="relative ml-auto w-full max-w-5xl h-full bg-gray-950 border-l border-gray-800 flex flex-col overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 flex-shrink-0">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-white truncate">{log.project_name}</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {new Date(log.created_at).toLocaleString()} · {log.inputs.ad_format}
            </p>
          </div>
          <button
            onClick={onClose}
            className="ml-4 p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition"
          >
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-gray-800">
            {/* Left column: inputs + prompts + copy */}
            <div className="p-6 space-y-4 overflow-y-auto">
              <Section title="Inputs">
                <KV label="Product" value={log.inputs.product_name} />
                <KV label="Description" value={log.inputs.description} />
                <KV label="Ad format" value={log.inputs.ad_format} />
                <KV label="Product images" value={log.inputs.has_product_images ? "Yes" : "No"} />
                <KV label="Reference images" value={log.inputs.has_ref_images ? "Yes" : "No"} />
              </Section>

              <Section title="Generated Copy">
                <KV label="Headline" value={log.ad_copy.headline} />
                <KV label="Body copy" value={log.ad_copy.body_copy} />
                <KV label="CTA" value={log.ad_copy.cta} />
              </Section>

              <Section title="Prompts" defaultOpen={false}>
                <div className="space-y-3">
                  <Mono label="System prompt" value={log.prompts.system_prompt} />
                  <Mono label="User brief" value={log.prompts.user_brief} />
                  {log.prompts.style_context && (
                    <Mono label="Extracted style context" value={log.prompts.style_context} />
                  )}
                  <Mono label="Image prompt" value={log.prompts.image_prompt} />
                </div>
              </Section>
            </div>

            {/* Right column: images + eval */}
            <div className="p-6 space-y-6 overflow-y-auto">
              {/* Images */}
              <div>
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  Generated Images
                </p>
                {doneImages.length === 0 ? (
                  <p className="text-sm text-gray-600">No completed images.</p>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {doneImages.map((img) => (
                      <button
                        key={img.id}
                        onClick={() => setExpandedImage(img.creative_url)}
                        className="relative rounded-lg overflow-hidden border border-gray-800 hover:border-gray-600 transition aspect-square bg-gray-900"
                      >
                        <img
                          src={img.creative_url ?? undefined}
                          alt={`Variation ${img.generated?.variation_index ?? '?'}`}
                          className="w-full h-full object-cover"
                        />
                        <span className="absolute top-1.5 left-1.5 bg-black/60 text-white text-xs px-1.5 py-0.5 rounded">
                          Var {img.generated?.variation_index ?? '?'}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Eval */}
              <div>
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  Evaluation
                </p>
                <div className="space-y-4">
                  {criteria.map((c, idx) => (
                    <div key={c.name} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-sm text-gray-300">{c.name}</label>
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            min={1}
                            max={10}
                            step={0.5}
                            placeholder="—"
                            value={c.score ?? ""}
                            onChange={(e) => handleScoreChange(idx, e.target.value)}
                            className="w-16 bg-gray-900 border border-gray-700 rounded-lg px-2 py-1 text-sm text-white text-center focus:outline-none focus:border-violet-500"
                          />
                          <span className="text-xs text-gray-600">/ 10</span>
                        </div>
                      </div>
                      <input
                        type="text"
                        placeholder="Notes (optional)"
                        value={c.notes}
                        onChange={(e) => handleNotesChange(idx, e.target.value)}
                        className="w-full bg-gray-900 border border-gray-800 rounded-lg px-3 py-1.5 text-xs text-gray-300 placeholder-gray-600 focus:outline-none focus:border-gray-700"
                      />
                    </div>
                  ))}

                  <div>
                    <label className="text-sm text-gray-300 block mb-1.5">Overall notes</label>
                    <textarea
                      rows={3}
                      placeholder="General observations, context, comparison notes…"
                      value={overallNotes}
                      onChange={(e) => setOverallNotes(e.target.value)}
                      className="w-full bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-300 placeholder-gray-600 focus:outline-none focus:border-gray-700 resize-none"
                    />
                  </div>

                  {saveError && (
                    <p className="text-xs text-red-400">{saveError}</p>
                  )}

                  <button
                    onClick={handleSave}
                    disabled={isSaving}
                    className="w-full py-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm font-medium transition"
                  >
                    {isSaving ? "Saving…" : "Save Scores"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Full-screen image preview */}
      {expandedImage && (
        <div
          className="absolute inset-0 z-10 flex items-center justify-center bg-black/80"
          onClick={() => setExpandedImage(null)}
        >
          <img
            src={expandedImage}
            alt="Preview"
            className="max-h-[90vh] max-w-[90vw] object-contain rounded-lg shadow-2xl"
          />
        </div>
      )}
    </div>
  );
}
