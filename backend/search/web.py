from __future__ import annotations

from services.image_search import search_and_fetch_product_image


class WebImageSearch:
    async def find(
        self,
        product_name: str,
        description: str,
        ad_copy_text: str,
        persona_info: str,
        creative_strategy: str,
    ) -> tuple[bytes, str] | None:
        return await search_and_fetch_product_image(
            product_name=product_name,
            description=description,
            ad_copy_text=ad_copy_text,
            persona_info=persona_info,
            creative_strategy=creative_strategy,
        )
