from __future__ import annotations

from jinja2 import Environment, PackageLoader

from core.protocols import PromptStrategy  # type: ignore


class V2Strategy:
    _env = Environment(loader=PackageLoader("strategies", "templates/v2"))

    # ── Taxonomy ──────────────────────────────────────────────────────────────

    def _taxonomy(
        self,
        has_ref_images: bool,
        has_logo_images: bool,
        for_image_prompt: bool = False,
        has_product_images: bool = True,
    ) -> str:
        if has_ref_images:
            if for_image_prompt:
                ref_block = (
                    "Multiple image types are attached with distinct roles:\n\n"
                    "IMAGE TYPE A — PRODUCT IMAGES (primary visual source):\n"
                    "  Source ALL background scenes, environments, hero visuals, and colour palette from these images only.\n\n"
                    "IMAGE TYPE B — REFERENCE AD (layout & style template):\n"
                    "  Replicate its full visual structure exactly: zone positions, panel splits, graphic elements,\n"
                    "  typography hierarchy, colours, dividers, overlays, and spacing rhythm.\n"
                    "  Replace only: background/hero visual (→ use Type A), logo (→ use Type C or Type A), ad copy (→ use approved copy)."
                )
            else:
                ref_block = (
                    "Two image types are attached. They have completely different roles:\n\n"
                    "IMAGE TYPE A — PRODUCT IMAGES (primary visual source — shown first):\n"
                    "  MANDATORY: All visual content in the final ad must come from these images.\n"
                    "  Use them for: background scene, environment, hero visual, brand logo (reproduce exactly as shown),\n"
                    "  and colour palette. These images supply 100% of the visuals — nothing else does.\n\n"
                    "IMAGE TYPE B — REFERENCE AD (layout wireframe only — zero visual content carried over):\n"
                    "  Use this ONLY to extract the abstract layout grid: where zones sit (logo, headline, body, CTA,\n"
                    "  detail strip), text layer count, and spacing rhythm.\n"
                    "  FORBIDDEN — do NOT use from this image:\n"
                    "    - Background, sky, landscape, environment\n"
                    "    - Any building, property, or product shown\n"
                    "    - Logo or brand marks\n"
                    "    - Colours, textures, overlays, graphics\n"
                    "  Treat it as a blank wireframe. Every pixel is discarded."
                )
        else:
            _single_hero = (
                "\nSINGLE HERO VISUAL (ABSOLUTE): Use ONE continuous background scene — no collages, "
                "split panels, stacked photos, or multi-image compositions."
            )
            if has_product_images:
                ref_block = (
                    "Product images are attached — use them as the primary visual source.\n"
                    "No reference ad provided. Use an elegant, clean, performance-optimised layout. Aspirational premium mood."
                    + _single_hero
                )
            else:
                ref_block = (
                    "No product images or reference ad provided. Generate visuals based entirely on the product description.\n"
                    "Do not hallucinate specific buildings, people, logos, or branded elements not mentioned in the brief.\n"
                    "Use an elegant, aspirational composition with a clean layout."
                    + _single_hero
                )

        logo_block = (
            "\nIMAGE TYPE C — BRAND LOGO (exact reproduction required):\n"
            "  This is the official logo. Reproduce it exactly as shown — no colour, proportion, or\n"
            "  typography changes. Place it in the brand corner of the ad. Do NOT use any logo from\n"
            "  Type A or Type B images when a Type C logo is provided."
            if has_logo_images
            else (
                "\nLOGO (no logo image provided):\n"
                "  Identify the real estate developer or brand from the project name and description.\n"
                "  Render their authentic logo accurately — correct colours, wordmark, icon, and proportions\n"
                "  as the brand is publicly known. Place it in the brand corner (top-left or top-right).\n"
                "  If the developer cannot be confidently identified, omit the logo entirely rather than inventing one."
            )
        )

        return f"{ref_block}{logo_block}"

    # ── Helper: flatten brand_info ────────────────────────────────────────────

    @staticmethod
    def _flatten_brand(brand_info) -> dict:
        if brand_info is None:
            return {}

        def _get(key):
            if isinstance(brand_info, dict):
                return brand_info.get(key)
            return getattr(brand_info, key, None)

        return {
            "brand_company": _get("company_name") or "",
            "brand_tagline": _get("tagline") or "",
            "brand_voice": _get("brand_voice") or "",
            "brand_industry": _get("industry") or "",
            "brand_personas": _get("target_personas") or [],
        }

    # ── Helper: compute aspect ────────────────────────────────────────────────

    @staticmethod
    def _aspect(ad_format: str) -> str:
        try:
            w, h = ad_format.lower().split("x")
            return "square" if w == h else ("landscape" if int(w) > int(h) else "portrait / story")
        except Exception:
            return "square"

    # ── Protocol methods ──────────────────────────────────────────────────────

    def build_copy_system_prompt(self, context: dict) -> str:
        taxonomy = self._taxonomy(
            has_ref_images=context.get("has_ref_images", False),
            has_logo_images=context.get("has_logo_images", False),
            has_product_images=context.get("has_product_images", True),
        )
        return self._env.get_template("copy_system.j2").render({**context, "taxonomy": taxonomy})

    def build_copy_user_brief(self, context: dict) -> str:
        brand_flat = self._flatten_brand(context.get("brand_info"))
        aspect = self._aspect(context.get("ad_format", ""))
        return self._env.get_template("copy_user.j2").render({
            **context,
            **brand_flat,
            "aspect": aspect,
        })

    def build_image_prompt_system(self, context: dict) -> str:
        has_product_images = context.get("has_product_images", True)
        taxonomy = self._taxonomy(
            has_ref_images=context.get("has_ref_images", False),
            has_logo_images=context.get("has_logo_images", False),
            for_image_prompt=True,
            has_product_images=has_product_images,
        )
        visual_source = (
            "derived from the product images (Type A)"
            if has_product_images
            else "generated from the product description"
        )
        logo_source = (
            "reproduce exactly from the logo image (Type C); never invent or borrow from the reference ad"
            if context.get("has_logo_images")
            else "identify the real estate developer from the project name and description, then render their authentic logo accurately; omit entirely if the developer cannot be confidently identified"
        )
        return self._env.get_template("image_prompt_system.j2").render({
            **context,
            "taxonomy": taxonomy,
            "visual_source": visual_source,
            "logo_source": logo_source,
        })

    def build_meta_copy_system(self, context: dict) -> str:
        return self._env.get_template("meta_copy_system.j2").render(context)

    def build_image_prompt_brief(self, context: dict) -> str:
        brand_flat = self._flatten_brand(context.get("brand_info"))
        aspect = self._aspect(context.get("ad_format", ""))
        return self._env.get_template("image_prompt_brief.j2").render({
            **context,
            **brand_flat,
            "aspect": aspect,
        })

    def build_image_gen_system(self, context: dict) -> str:
        return self._env.get_template("image_gen_system.j2").render(context)

    def build_image_gen_prompt(self, base_prompt: str, ad_copy, variation_index: int) -> str:
        hints = self.variation_hints()
        hint = ""
        copy_override = ""
        if ad_copy and ad_copy.variations:
            var = ad_copy.variations[variation_index % len(ad_copy.variations)]
            hint = f" {var.visual_hint}".rstrip() if var.visual_hint else hints[variation_index % len(hints)]
            copy_override = (
                f"\nCopy for this variation (render verbatim on the image):"
                f'\n  Headline: "{var.headline}"'
                f'\n  Body copy: "{var.body_copy}"'
                f'\n  CTA: "{ad_copy.cta}"'
            )
        else:
            hint = hints[variation_index % len(hints)] if hints else ""
        return f"{base_prompt}{hint}{copy_override}".strip()

    def variation_hints(self) -> list[str]:
        return [
            "",
            " Alternate layout: pricing and configuration details left-aligned, bold headline right, strong negative space.",
            " High-contrast dramatic lighting, deep shadows with sharp product highlight.",
            " Aspirational lifestyle context, warm ambient environment, human presence implied.",
        ]
