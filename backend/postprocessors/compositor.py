from __future__ import annotations
import asyncio
from core.protocols import CreativeContext
from services.compositor import overlay_rera_and_qr


class RERACompositor:
    async def process(self, image_bytes: bytes, context: CreativeContext) -> bytes:
        return await asyncio.to_thread(
            overlay_rera_and_qr,
            image_bytes,
            context.rera_number,
            context.qr_code_bytes,
        )
