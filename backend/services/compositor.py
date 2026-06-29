import io
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageStat
from fastapi import HTTPException, UploadFile
import puremagic

logger = logging.getLogger("revCreate.compositor")

_FONT_CANDIDATES = [
    # Installed by fonts-dejavu-core (Debian/Ubuntu/python:slim Docker image)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # Amazon Linux / RHEL
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    # macOS (development)
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    logger.warning("No scalable font found — falling back to bitmap default (font size ignored)")
    return ImageFont.load_default()

async def validate_qr_upload(file: UploadFile | None) -> bytes | None:
    if not file or not file.filename:
        return None

    # 5MB Limit
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="QR code file too large (max 5MB)")

    # Validate format using puremagic
    try:
        magic_info = puremagic.magic_string(content)
        ext = magic_info[0].extension.lower()
        if ext not in ['.jpeg', '.jpg', '.png', '.webp']:
            raise HTTPException(status_code=400, detail="QR code must be a JPEG, PNG, or WEBP image")
    except puremagic.PureError:
        raise HTTPException(status_code=400, detail="Invalid image file for QR code")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=400, detail="Failed to validate image file")

    return content


# def _region_has_content(gray_region: "Image.Image") -> bool:
#     """
#     Returns True if a corner region contains text OR sharp graphic content
#     (logos, QR codes, icons) that would be obscured by the overlay.
#
#     Two signals combined:
#     1. Bimodal row-edge distribution  → printed/rendered text
#     2. High density of very strong edges → logos, QR codes, icons
#     """
#     edges = gray_region.filter(ImageFilter.FIND_EDGES)
#     w, h = gray_region.size
#     if h == 0 or w == 0:
#         return False
#
#     # Signal 1: text bimodality
#     step = max(1, h // 40)
#     row_means: list[float] = []
#     for y in range(0, h, step):
#         row = edges.crop((0, y, w, min(y + 1, h)))
#         row_means.append(ImageStat.Stat(row).mean[0])
#     n = len(row_means)
#     mu = sum(row_means) / n if n else 0
#     if mu >= 3:
#         std = (sum((v - mu) ** 2 for v in row_means) / n) ** 0.5
#         if std > 14:
#             return True
#
#     # Signal 2: very dense sharp edges (QR codes, high-contrast logos)
#     hist = edges.histogram()
#     strong = sum(hist[70:])
#     total = w * h
#     if strong / total > 0.20:
#         return True
#
#     return False


def overlay_rera_and_qr(
    image_bytes: bytes,
    rera_number: str | None = None,
    qr_code_bytes: bytes | None = None,
) -> bytes:
    if not rera_number and not qr_code_bytes:
        return image_bytes

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        width, height = img.size

        padding_x = int(width * 0.01)
        padding_y = int(height * 0.002)
        footer_height = int(height * 0.11)
        font_size = int(footer_height * 0.15)
        qr_size = int(footer_height * 0.50)
        qr_vpad = (footer_height - qr_size) // 2
        gap = int(width * 0.015)

        # Always place at bottom-right
        footer_top = height - footer_height - padding_y

        # # ── Region content detection (disabled) ──────────────────────────────
        # # Checks each corner for text/graphic content and picks the clearest.
        # def _box(align, top):
        #     x0 = (width - padding_x - total_block_width) if align == "right" else padding_x
        #     x1 = x0 + total_block_width
        #     return (max(0, x0), top, min(width, x1), top + footer_height)
        # br_top = height - footer_height - padding_y
        # tr_top = padding_y
        # candidates = [
        #     ("bottom-right", _box("right", br_top), br_top, "right"),
        #     ("bottom-left",  _box("left",  br_top), br_top, "left"),
        #     ("top-right",    _box("right", tr_top), tr_top, "right"),
        #     ("top-left",     _box("left",  tr_top), tr_top, "left"),
        # ]
        # for name, crop_box, top, al in candidates:
        #     if not _region_has_content(img.crop(crop_box).convert("L")):
        #         footer_top, align = top, al
        #         break

        # Brightness of bottom-right region → text color
        check = img.crop((width // 2, footer_top, width, height)).convert("L")
        is_light = ImageStat.Stat(check).mean[0] > 10

        # Create overlay
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        text_color = (255, 255, 255, 255) if is_light else (0, 0, 0, 255)

        # Measure text width
        font = None
        text_width = 0
        if rera_number:
            font = _load_font(font_size)
            rera_display = f"RERA: {rera_number}"
            b = font.getbbox(rera_display)
            text_width = b[2] - b[0]

        total_block_width = (text_width
                             + (gap if rera_number and qr_code_bytes else 0)
                             + (qr_size if qr_code_bytes else 0))

        cursor_x = width - padding_x - total_block_width

        # Render RERA text
        if rera_number and font:
            text_y = footer_top + (footer_height - font_size) // 2
            draw.text((cursor_x, text_y), rera_display, font=font, fill=text_color)
            cursor_x += text_width + gap

        # Render QR immediately right of RERA text
        if qr_code_bytes:
            qr_img = Image.open(io.BytesIO(qr_code_bytes)).convert("RGBA")
            qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
            qr_y = footer_top + qr_vpad
            overlay.paste(qr_img, (cursor_x, qr_y), qr_img)

        # Composite and return
        final_img = Image.alpha_composite(img, overlay).convert("RGB")
        out_bytes = io.BytesIO()
        final_img.save(out_bytes, format="JPEG", quality=95)
        return out_bytes.getvalue()

    except Exception as e:
        logger.error(f"Compositing failed: {e}", exc_info=True)
        return image_bytes
