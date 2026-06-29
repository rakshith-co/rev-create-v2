"""
Standalone visual test for the compositor.
Run from backend/ directory:
    python -m tests.compositor_visual_test

Outputs compositor_test_output/ with one image per test case.
"""

import io
import os
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from services.compositor import overlay_rera_and_qr

OUT_DIR = os.path.join(os.path.dirname(__file__), "compositor_test_output")
os.makedirs(OUT_DIR, exist_ok=True)

RERA = "P51800012345"
IMAGE_SIZE = (1080, 1350)  # 4:5 portrait, typical real-estate ad


def _save(name: str, img_bytes: bytes):
    path = os.path.join(OUT_DIR, name)
    with open(path, "wb") as f:
        f.write(img_bytes)
    print(f"  saved → {path}")


def _make_image(bg: str = "white", add_bottom_text: bool = False) -> bytes:
    """Synthetic ad image with optional text near the bottom-right."""
    img = Image.new("RGB", IMAGE_SIZE, bg)
    draw = ImageDraw.Draw(img)

    # Fake ad content block in the upper area
    accent = "#1a237e" if bg == "white" else "#ffd740"
    draw.rectangle([60, 60, IMAGE_SIZE[0] - 60, 900], outline=accent, width=6)
    try:
        font_big = ImageFont.truetype("Arial", 72)
        font_sm = ImageFont.truetype("Arial", 36)
    except IOError:
        font_big = font_sm = ImageFont.load_default()

    fill = "black" if bg == "white" else "white"
    draw.text((120, 120), "Luxury 3BHK Apartments", font=font_big, fill=fill)
    draw.text((120, 220), "₹1.2 Cr onwards  |  Possession Dec 2026", font=font_sm, fill=fill)
    draw.text((120, 290), "Whitefield, Bangalore  |  2BHK / 3BHK / 4BHK", font=font_sm, fill=fill)
    draw.text((120, 800), "KNOW MORE →", font=font_sm, fill=accent)

    if add_bottom_text:
        # Simulate text/visual bleeding into bottom-right (what edge detection should catch)
        draw.text((IMAGE_SIZE[0] - 400, IMAGE_SIZE[1] - 120), "Fine print here", font=font_sm, fill=fill)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _make_qr() -> bytes:
    """Minimal checkerboard QR-lookalike."""
    size = 200
    qr = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(qr)
    cell = size // 10
    for r in range(10):
        for c in range(10):
            if (r + c) % 2 == 0:
                d.rectangle([c * cell, r * cell, (c + 1) * cell - 1, (r + 1) * cell - 1], fill="black")
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    return buf.getvalue()


def run():
    qr_bytes = _make_qr()

    cases = [
        ("01_rera_only_light",        _make_image("white"),           RERA,  None),
        ("02_rera_only_dark",         _make_image("#1a1a2e"),         RERA,  None),
        ("03_qr_only",                _make_image("white"),           None,  qr_bytes),
        ("04_rera_and_qr_light",      _make_image("white"),           RERA,  qr_bytes),
        ("05_rera_and_qr_dark",       _make_image("#1a1a2e"),         RERA,  qr_bytes),
        ("06_busy_bottomright_light", _make_image("white", True),     RERA,  qr_bytes),
        ("07_busy_bottomright_dark",  _make_image("#1a1a2e", True),   RERA,  qr_bytes),
    ]

    print(f"\nRunning {len(cases)} compositor test cases → {OUT_DIR}\n")
    for name, img_bytes, rera, qr in cases:
        print(f"  [{name}]")
        result = overlay_rera_and_qr(img_bytes, rera, qr)
        _save(f"{name}.jpg", result)

    print("\nDone. Open compositor_test_output/ to review.\n")


if __name__ == "__main__":
    run()
