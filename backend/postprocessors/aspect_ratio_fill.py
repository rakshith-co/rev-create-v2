from __future__ import annotations

import asyncio

from core.protocols import CreativeContext
from services.aspect_ratio_fill import apply_blur_fill


class AspectRatioFillProcessor:
    async def process(self, image_bytes: bytes, context: CreativeContext) -> bytes:
        return await asyncio.to_thread(apply_blur_fill, image_bytes, context.ad_format)
