from __future__ import annotations


class NoOpSearch:
    async def find(
        self,
        product_name: str,
        description: str,
        ad_copy_text: str,
        persona_info: str,
        creative_strategy: str,
    ) -> tuple[bytes, str] | None:
        return None
