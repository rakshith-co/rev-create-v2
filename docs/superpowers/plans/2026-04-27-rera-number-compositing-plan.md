# RERA Number & QR Code Compositing Implementation Plan

> **For Gemini:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a Pillow-based compositor to overlay RERA numbers and QR codes onto generated ad creatives, preventing LLM hallucinations.

**Architecture:** We will introduce a new `compositor.py` module to handle Pillow image manipulation. The router endpoints (`/generate`, `/fb-banner`) will be updated to accept an optional QR code upload, which will be validated and passed down through the `PipelineInputs` context. The compositor will be called in `pipeline.py` immediately after the image generation step, executing in an `asyncio.to_thread` block to remain non-blocking. Prompt builder modules will have their RERA generation instructions stripped and replaced with negative constraints.

**Tech Stack:** FastAPI, Pillow (PIL), asyncio

---

### Task 1: Create the Compositor Logic

**Files:**
- Create: `backend/services/compositor.py`
- Create: `backend/tests/test_compositor.py`

**Step 1: Write the failing test**

```python
import io
import pytest
from PIL import Image
from services.compositor import overlay_rera_and_qr

def create_test_image(color="white", size=(1080, 1080)):
    img = Image.new("RGB", size, color)
    b = io.BytesIO()
    img.save(b, format="JPEG")
    return b.getvalue()

def test_overlay_bypassed_if_no_inputs():
    img_bytes = create_test_image()
    res = overlay_rera_and_qr(img_bytes, None, None)
    assert res == img_bytes

def test_overlay_handles_dark_background():
    img_bytes = create_test_image("black")
    # Expected: Light overlay rgba(255, 255, 255, 160)
    res = overlay_rera_and_qr(img_bytes, "RERA123", None)
    assert res != img_bytes

def test_overlay_handles_light_background():
    img_bytes = create_test_image("white")
    # Expected: Dark overlay rgba(0, 0, 0, 160)
    res = overlay_rera_and_qr(img_bytes, "RERA123", None)
    assert res != img_bytes
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_compositor.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

**Step 3: Write minimal implementation**

Create `backend/services/compositor.py`:
```python
import io
import logging
from PIL import Image, ImageDraw, ImageFont, ImageStat

logger = logging.getLogger("revCreate.compositor")

def overlay_rera_and_qr(
    image_bytes: bytes,
    rera_number: str | None = None,
    qr_code_bytes: bytes | None = None
) -> bytes:
    if not rera_number and not qr_code_bytes:
        return image_bytes

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        width, height = img.size
        
        # Footer dimensions: 12% of height
        footer_height = int(height * 0.12)
        footer_top = height - footer_height
        
        # Analyze bottom 12% brightness
        bottom_region = img.crop((0, footer_top, width, height)).convert("L")
        stat = ImageStat.Stat(bottom_region)
        is_light = stat.mean[0] > 127
        
        # Create overlay
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Determine colors based on brightness
        if is_light:
            bg_color = (0, 0, 0, 160)
            text_color = (255, 255, 255, 255)
        else:
            bg_color = (255, 255, 255, 160)
            text_color = (0, 0, 0, 255)
            
        draw.rectangle([0, footer_top, width, height], fill=bg_color)
        
        # Render RERA on the left
        if rera_number:
            try:
                # Try common system font, fallback to default
                font_size = int(footer_height * 0.4)
                font = ImageFont.truetype("Arial", font_size)
            except IOError:
                font = ImageFont.load_default()
            
            # Simple text positioning: 5% padding from left, centered vertically in footer
            padding_x = int(width * 0.05)
            # Use getbbox or similar for better centering in production
            text_y = footer_top + (footer_height // 2) - (font_size // 2)
            draw.text((padding_x, text_y), f"RERA: {rera_number}", font=font, fill=text_color)
            
        # Render QR on the right
        if qr_code_bytes:
            qr_img = Image.open(io.BytesIO(qr_code_bytes)).convert("RGBA")
            # Resize QR to fit footer with 10% proportional padding
            qr_pad = int(footer_height * 0.1)
            qr_size = footer_height - (qr_pad * 2)
            qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
            
            # Position QR on the right
            qr_x = width - qr_size - int(width * 0.05)
            qr_y = footer_top + qr_pad
            
            # Add to overlay
            overlay.paste(qr_img, (qr_x, qr_y), qr_img)
            
        # Composite and return
        final_img = Image.alpha_composite(img, overlay).convert("RGB") # Convert back to RGB for JPEG saving
        out_bytes = io.BytesIO()
        final_img.save(out_bytes, format="JPEG", quality=95)
        return out_bytes.getvalue()
        
    except Exception as e:
        logger.error(f"Compositing failed: {e}", exc_info=True)
        return image_bytes # Fallback to original
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_compositor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/compositor.py backend/tests/test_compositor.py
git commit -m "feat: add robust Pillow compositor for RERA and QR overlays"
```

---

### Task 2: Update Prompt Builders

**Files:**
- Modify: `backend/services/prompt_builder.py`
- Modify: `backend/services/prompt_builder_v2.py`

**Step 1: Write the failing test / Verify Current Behavior**

(We don't need dedicated failing tests for string manipulation here, we just need to ensure the system prompts no longer ask the LLM to generate RERA)

**Step 2: Modify prompt_builder.py**

Modify `build_image_generation_system_prompt()` to add negative constraint:
```python
def build_image_generation_system_prompt() -> str:
    return (
        "You are an expert ad creative generator. "
        "You receive product images, a reference ad for layout structure, and a creative brief. "
        "ABSOLUTE RULE — TEXT CONTENT: Every word, number, and character rendered in the generated image "
        "must come exclusively from the creative brief in the prompt. "
        "NEVER copy any text from the reference ad — this includes RERA numbers, website URLs, "
        "phone numbers, email addresses, project names, taglines, slogans, disclaimers, prices, "
        "or any other written content visible in the reference ad. "
        "If a text element from the reference ad has no counterpart in the brief, omit it entirely. "
        "The reference ad is a layout and style template only — replicate its structure, discard all its text. "
        "CRITICAL: Do NOT attempt to render any RERA or registration numbers on the canvas yourself. Keep the bottom 12% of the canvas clean for system-applied overlays."
    )
```

Modify `build_image_prompt_brief()` to remove the RERA note:
```python
# Remove the old rera_note logic:
# rera_note = (
#     f"\nRERA Registration: {rera_number} — MANDATORY: render this verbatim at the very bottom..."
# )

# And remove it from the returned string:
return f"""Approved copy:
  Headline: "{headline}"
  Body copy: "{body_copy}"
  CTA: "{cta}"{product_note}{logo_note}{brand_section}

Ad format: {ad_format} ({aspect}){ref_note}

Write the image_prompt."""
```

*(Repeat similar removal logic in `prompt_builder_v2.py` if present)*

**Step 3: Run existing tests to verify no breaks**

Run: `pytest backend/tests/ -v`

**Step 4: Commit**

```bash
git add backend/services/prompt_builder.py backend/services/prompt_builder_v2.py
git commit -m "refactor: remove RERA generation from prompts, add negative constraints"
```

---

### Task 3: Update API Router to Accept QR Upload

**Files:**
- Modify: `backend/routers/generate.py`
- Modify: `backend/routers/fb_form_banner.py`

**Step 1: Write minimal implementation in `generate.py`**

```python
# Add imports if missing:
from fastapi import File, UploadFile, HTTPException
import imghdr

# Add new validation function at the top level or in a utils file
def validate_qr_upload(file: UploadFile | None) -> bytes | None:
    if not file:
        return None
    
    # 5MB Limit
    content = file.file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="QR code file too large (max 5MB)")
    
    # Validate mime type
    image_type = imghdr.what(None, h=content)
    if image_type not in ['jpeg', 'png', 'webp']:
        raise HTTPException(status_code=400, detail="QR code must be a JPEG, PNG, or WEBP image")
        
    return content


# Update endpoint signature
async def generate(
    ...
    # New parameter:
    qr_code: Optional[UploadFile] = File(None),
):
    ...
    # Inside the function, right before building associations:
    qr_code_bytes = validate_qr_upload(qr_code)
```

*(Apply exact same logic to `/fb-banner` in `fb_form_banner.py`)*

**Step 2: Run test/type check to verify**

Run: `cd backend && python -m py_compile routers/generate.py routers/fb_form_banner.py`

**Step 3: Commit**

```bash
git add backend/routers/generate.py backend/routers/fb_form_banner.py
git commit -m "feat: add optional QR code upload and validation to generate endpoints"
```

---

### Task 4: Integrate Compositor into Pipeline

**Files:**
- Modify: `backend/services/pipeline.py`

**Step 1: Write minimal implementation**

```python
# 1. Update PipelineInputs dataclass:
@dataclass
class PipelineInputs:
    ...
    # Add new fields
    rera_number: Optional[str] = None
    qr_code_bytes: Optional[bytes] = None

# 2. Update run_pipeline_core to accept and pass through QR
async def run_pipeline_core(
    project_id: str,
    inputs: PipelineInputs,
    ...
):
    ...
    # Right after we extract RERA, make sure it's stored in inputs if not already
    rera_num = extract_rera_number(inputs.description)
    if rera_num:
         inputs.rera_number = rera_num
         
    ...
    # Inside _gen_one:
    async def _gen_one(img_id: str, variation_index: int, prompt: str) -> None:
         ...
         res = await generate_image(...)
         img_bytes = base64.b64decode(res["image_base64"])
         
         # NEW: Call Compositor
         from services.compositor import overlay_rera_and_qr
         img_bytes = await asyncio.to_thread(
             overlay_rera_and_qr, 
             img_bytes, 
             inputs.rera_number, 
             inputs.qr_code_bytes
         )
         ...
```

**Step 2: Update Routers to pass the QR to Pipeline**

In `backend/routers/generate.py` and `backend/routers/fb_form_banner.py`, ensure `qr_code_bytes` is passed into `PipelineInputs`.

```python
# In routers/generate.py:
    inputs = PipelineInputs(
        ...
        qr_code_bytes=qr_code_bytes
    )
```

**Step 3: Run existing tests to verify**

Run: `pytest backend/tests/ -v`

**Step 4: Commit**

```bash
git add backend/services/pipeline.py backend/routers/generate.py backend/routers/fb_form_banner.py
git commit -m "feat: integrate compositor into main image generation pipeline"
```
