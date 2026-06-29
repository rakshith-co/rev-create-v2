import React, { useRef, useState } from "react";
import { GenerateFormData } from "../types";

interface Props {
  data: GenerateFormData;
  onChange: (field: keyof GenerateFormData, value: string | File[]) => void;
}

// ── reusable image upload zone ────────────────────────────────────────────────

export function ImageUploadZone({
  images,
  onAdd,
  onRemove,
}: {
  images: File[];
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const valid = Array.from(files).filter((f) =>
      ["image/jpeg", "image/png", "image/webp"].includes(f.type)
    );
    if (valid.length) onAdd(valid);
  };

  return (
    <div>
      <div
        onClick={() => inputRef.current?.click()}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          addFiles(e.dataTransfer.files);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        className={[
          "border-2 border-dashed rounded-xl py-8 text-center cursor-pointer transition select-none",
          isDragging
            ? "border-violet-500 bg-violet-500/10"
            : "border-gray-700 hover:border-gray-600 hover:bg-gray-800/40",
        ].join(" ")}
      >
        <svg
          className="mx-auto mb-2 h-6 w-6 text-gray-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
          />
        </svg>
        <p className="text-sm text-gray-400">
          Drop images here or{" "}
          <span className="text-violet-400 font-medium">click to browse</span>
        </p>
        <p className="text-xs text-gray-600 mt-1">JPG, PNG, WebP</p>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          className="hidden"
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {images.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {images.map((file, i) => (
            <div key={i} className="relative group">
              <img
                src={URL.createObjectURL(file)}
                alt={file.name}
                className="h-16 w-16 object-cover rounded-lg border border-gray-700"
              />
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onRemove(i);
                }}
                className="absolute -top-1.5 -right-1.5 bg-red-600 hover:bg-red-500 text-white
                           rounded-full w-5 h-5 text-xs flex items-center justify-center
                           opacity-0 group-hover:opacity-100 transition shadow"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── main form ─────────────────────────────────────────────────────────────────

export default function CreateProjectForm({ data, onChange }: Props) {
  const handleReraToggle = (e: React.ChangeEvent<HTMLInputElement>) => {
    const checked = e.target.checked;
    onChange("enable_rera", checked as any);
    if (!checked) {
      onChange("qr_code", null as any);
    }
  };

  return (
    <div className="space-y-5">
      {/* ── Product Details ── */}
      <div className="section-card space-y-4">
        <p className="section-title">Product Details</p>

        <div>
          <label className="label">
            Product Name <span className="text-violet-400">*</span>
          </label>
          <input
            className="input"
            placeholder="e.g. AeroFlow Running Shoes"
            value={data.product_name}
            onChange={(e) => onChange("product_name", e.target.value)}
          />
        </div>

        <div>
          <label className="label">Description</label>
          <textarea
            className="input resize-none"
            rows={4}
            placeholder="What does your product do? Key features, benefits, target audience..."
            value={data.description}
            onChange={(e) => onChange("description", e.target.value)}
          />
        </div>

        <div>
          <label className="label">Product Images</label>
          <p className="text-xs text-gray-500 mb-2">
            Upload product photos — these will be placed directly into the ad creatives.
          </p>
          <ImageUploadZone
            images={data.product_images}
            onAdd={(files) =>
              onChange("product_images", [...data.product_images, ...files])
            }
            onRemove={(i) =>
              onChange(
                "product_images",
                data.product_images.filter((_, idx) => idx !== i)
              )
            }
          />
        </div>
      </div>

      {/* ── Reference Ads ── */}
      <div className="section-card space-y-4">
        <p className="section-title">Reference Ads</p>

        <div>
          <label className="label">Reference Ad Images</label>
          <p className="text-xs text-gray-500 mb-2">
            Upload existing brand ads as style references — the AI will closely follow these designs.
          </p>
          <ImageUploadZone
            images={data.ref_images}
            onAdd={(files) =>
              onChange("ref_images", [...data.ref_images, ...files])
            }
            onRemove={(i) =>
              onChange(
                "ref_images",
                data.ref_images.filter((_, idx) => idx !== i)
              )
            }
          />
        </div>
      </div>

      {/* ── Brand Logo ── */}
      <div className="section-card space-y-4">
        <div className="flex items-center justify-between">
          <p className="section-title">Brand Logo</p>
          <span className="text-xs text-gray-500">Optional</span>
        </div>

        <div>
          <label className="label">Logo Image</label>
          <p className="text-xs text-gray-500 mb-2">
            Upload the brand logo — it will be placed exactly as shown in all generated creatives.
          </p>
          <ImageUploadZone
            images={data.logo_images}
            onAdd={(files) =>
              onChange("logo_images", [...data.logo_images, ...files])
            }
            onRemove={(i) =>
              onChange(
                "logo_images",
                data.logo_images.filter((_, idx) => idx !== i)
              )
            }
          />
        </div>
      </div>

      {/* ── RERA & QR Code ── */}
      <div className="section-card space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <p className="section-title">RERA Compliance</p>
            <span className="text-[10px] bg-violet-500/20 text-violet-400 px-1.5 py-0.5 rounded border border-violet-500/30 uppercase font-bold tracking-wider">New</span>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              className="sr-only peer"
              checked={data.enable_rera}
              onChange={handleReraToggle}
            />
            <div className="w-9 h-5 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-violet-600"></div>
          </label>
        </div>

        {data.enable_rera && (
          <div className="pt-2 animate-in fade-in slide-in-from-top-2 duration-300">
            <label className="label">QR Code Image</label>
            <p className="text-xs text-gray-500 mb-2">
              If a RERA number is found in the description, it will be rendered in the footer. Upload a QR code here to display it on the right side of the footer.
            </p>
            <ImageUploadZone
              images={data.qr_code ? [data.qr_code] : []}
              onAdd={(files) => onChange("qr_code", files[0] as any)}
              onRemove={() => onChange("qr_code", null as any)}
            />
          </div>
        )}
      </div>

    </div>
  );
}
