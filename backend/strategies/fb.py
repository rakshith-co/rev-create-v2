from __future__ import annotations

from jinja2 import Environment, PackageLoader

from core.protocols import PromptStrategy  # type: ignore


class FBStrategy:
    _env = Environment(loader=PackageLoader("strategies", "templates/fb"))

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

    # ── Protocol methods ──────────────────────────────────────────────────────

    def build_copy_system_prompt(self, context: dict) -> str:
        return ""

    def build_copy_user_brief(self, context: dict) -> str:
        brand_flat = self._flatten_brand(context.get("brand_info"))
        return self._env.get_template("copy_user.j2").render({
            **context,
            **brand_flat,
        })

    def build_image_prompt_system(self, context: dict) -> str:
        # FB banners reuse copy_system.j2 — no separate image_prompt_system step
        return self._env.get_template("copy_system.j2").render(context)

    def build_meta_copy_system(self, context: dict) -> str:
        # FB banners do not produce Meta platform copy; return empty string
        return ""

    def build_image_prompt_brief(self, context: dict) -> str:
        brand_flat = self._flatten_brand(context.get("brand_info"))
        return self._env.get_template("copy_user.j2").render({
            **context,
            **brand_flat,
        })

    def build_image_gen_system(self, context: dict) -> str:
        # FB banner image gen: minimal banner with product hero and logo
        has_ref_images = context.get("has_ref_images", False)
        ref_note = (
            "You receive product images and a reference ad for layout/mood guidance. "
            if has_ref_images else
            "No reference ad provided — use full creative control. "
        )
        return (
            "You are an expert image generator specialising in Facebook Lead Ad form banners. "
            "Canvas: 1200×628px (1.91:1 landscape). "
            + ref_note +
            "\nCRITICAL RULES:"
            "\n  • Full-bleed product/property hero image ONLY. No text, logos, CTAs, badges, or graphic elements."
            "\n  • Mood: minimal, breathable, aspirational, trustworthy, premium."
            "\n  • NEVER include RERA numbers or any regulatory text."
        )

    def build_image_gen_prompt(self, base_prompt: str, ad_copy, variation_index: int) -> str:
        return base_prompt

    def variation_hints(self) -> list[str]:
        # FB lead ad banners produce a single creative, not 4 variations
        return [""]
