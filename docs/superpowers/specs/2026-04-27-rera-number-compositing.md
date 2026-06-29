# RERA Number & QR Code Compositing Design

## Overview
Currently, the pipeline attempts to include RERA numbers directly via the image generation prompts. This design changes that behavior: RERA numbers and a newly introduced optional QR code will be dynamically overlaid onto the final generated images using Pillow (PIL), and the image generation prompts will explicitly prohibit hallucinating RERA text.

## 1. API Updates & Data Flow
- **Endpoint Update:** The `/generate` and similar endpoints (e.g., `/fb-banner`) will be updated to accept an optional file upload: `qr_code: UploadFile | None = File(None)`.
- **Extraction:** The pipeline will continue to extract the RERA number from the brief/description (or use an explicit `rera_number` if provided). 
- **Routing:** Instead of passing the RERA number into the image prompt builders, both the RERA number and the optional QR code bytes will be retained in the pipeline context for the post-generation compositing step.

## 2. Prompt Builder Adjustments
- **Removal:** Remove existing instructions in `backend/services/prompt_builder*.py` that instruct the model to render the RERA number on the canvas.
- **Negative Prompting:** Explicitly add negative constraints instructing the model *not* to render any RERA, registration numbers, or placeholder texts to prevent hallucinations.

## 3. Compositing Logic (Pillow)
A new utility module (e.g., `backend/services/compositor.py`) will handle the image manipulation:
- It will accept the raw generated image bytes, the optional RERA number string, and the optional QR code bytes.
- **Conditional Logic:**
  - If neither a RERA number nor a QR code is present, bypass the compositing entirely.
  - If either is present, create a semi-transparent footer (12% of the image height, `rgba(0,0,0,160)`).
  - If the RERA number is present, render it in white text (Arial or default font) on the left side of the footer.
  - If the QR code is present, resize it to fit the footer height and paste it on the right side.
- It returns the modified image bytes.

## 4. Pipeline Integration
In the image generation orchestration (e.g., `backend/services/pipeline.py` and `pipeline_openai.py`), right after the image generation model yields the raw image bytes:
- The bytes will be passed through the new compositor function along with the RERA/QR data.
- The resulting bytes (whether modified or original) will then proceed to S3 upload and database storage as usual.
