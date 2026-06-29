from __future__ import annotations

import io

from PIL import Image, ImageFilter

_BLUR_RADIUS = 25


def apply_blur_fill(image_bytes: bytes, target_format: str) -> bytes:
    """Extend image to target_format ('WxH') using a blurred-background fill."""
    try:
        tw, th = (int(x) for x in target_format.lower().split("x"))
    except (ValueError, AttributeError):
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    iw, ih = img.size

    if iw == tw and ih == th:
        return image_bytes

    # Background: scale to cover target, center-crop, blur
    scale = max(tw / iw, th / ih)
    bg = img.resize((round(iw * scale), round(ih * scale)), Image.LANCZOS)
    bw, bh = bg.size
    left, top = (bw - tw) // 2, (bh - th) // 2
    bg = bg.crop((left, top, left + tw, top + th))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=_BLUR_RADIUS))

    # Foreground: scale to fit inside target, paste centered
    fit_scale = min(tw / iw, th / ih)
    fg = img.resize((round(iw * fit_scale), round(ih * fit_scale)), Image.LANCZOS)
    fw, fh = fg.size
    bg.paste(fg, ((tw - fw) // 2, (th - fh) // 2))

    out = io.BytesIO()
    bg.save(out, format="JPEG", quality=95)
    return out.getvalue()
