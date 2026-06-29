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
