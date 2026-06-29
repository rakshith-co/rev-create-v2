# RERA Number & QR Code Compositing Design (2026-04-27)

## Overview
Currently, the pipeline attempts to include RERA numbers directly via the image generation prompts, which leads to hallucinations and inconsistent rendering. This design moves RERA number and optional QR code placement to a post-generation compositing step using Pillow (PIL).

## 1. API Updates & Data Flow
- **Endpoint Updates:** `/generate` and `/fb-banner` will accept an optional `qr_code: UploadFile = File(None)`.
- **Validation:** Uploaded QR codes must be < 5MB and in a raster format (JPEG, PNG, WEBP).
- **Extraction:** The pipeline will extract the RERA number from the brief/description using `extract_rera_number`.
- **Context:** `PipelineInputs` will be extended to carry `qr_code_bytes: Optional[bytes]` and the extracted RERA string.

## 2. Prompt Builder Adjustments
- **Removal:** Remove RERA rendering instructions from `backend/services/prompt_builder*.py`.
- **Negative Prompting:** Explicitly instruct the model *not* to render any RERA, registration numbers, or placeholder text to prevent hallucinations.
- **Layout Clearances:** Update system prompts to signal that the bottom 12% of the canvas should be kept clear for system overlays.

## 3. Compositing Logic (`backend/services/compositor.py`)
A new utility module will handle the image manipulation:
- **Dynamic Footer:** 
    - Analyzes the bottom 12% of the generated image for brightness.
    - **Dark Overlay:** `rgba(0,0,0,160)` with white text for light backgrounds.
    - **Light Overlay:** `rgba(255,255,255,160)` with black text for dark backgrounds.
- **RERA Rendering:** Rendered on the left side of the footer, vertically centered.
- **QR Code Rendering:** 
    - Resized to fit the footer height with 10% proportional padding.
    - Composited on the right side of the footer.
- **Non-Blocking:** Executed via `asyncio.to_thread()` to prevent blocking the event loop.

## 4. Pipeline Integration
In `backend/services/pipeline.py`, immediately after image generation:
- The raw bytes pass through the compositor.
- **Fault Tolerance:** If compositing fails, the error is logged, and the original un-composited image is used as a fallback to avoid failing the entire generation.
- Modified (or original) bytes proceed to S3 upload and DB storage.

## 5. Success Criteria
- RERA numbers are rendered with 100% accuracy and legibility.
- QR codes are correctly placed and scannable.
- The image generation model no longer attempts to hallucinate its own registration text.
