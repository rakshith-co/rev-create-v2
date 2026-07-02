"""Atelier prompt strategy — the V2 "own marketing studio" path.

Mechanism (see docs/architecture.md): a format library of worded layout
blueprints (backend/formats/) + product-image conditioning + one image pass.
Maps onto the existing pipeline with no pipeline changes:

  GENERATING_META_COPY    build_meta_copy_system      Meta platform copy (4 variations)
  GENERATING_COPY         build_copy_system_prompt    on-image copy, AdCopy JSON contract
  GENERATING_IMAGE_PROMPT build_image_prompt_system   SELECT one format from the library
                                                      and emit the assembled blueprint
  GENERATING_IMAGES       build_image_gen_system      fixed creative-director system
                          build_image_gen_prompt      blueprint + verbatim copy + variation hint

The image-prompt LLM returns "[format: <id>]" on its first line; the marker is
stripped before the prompt reaches the image model but survives in
context.image_prompt for observability.
"""
from __future__ import annotations

import re

from formats.loader import format_menu

# Formats below this real-estate relevance are left out of the selector menu.
MIN_FORMAT_RELEVANCE = 6

_FORMAT_MARKER = re.compile(r"^\s*\[format:\s*(?P<id>[a-z0-9_]+)\s*\]\s*\n?", re.IGNORECASE)

_SYSTEM_IDENTITY = (
    "You are an award-winning creative director at a premium real-estate "
    "advertising studio. Your statics win Meta auctions for ₹1Cr+ residential "
    "projects because they read as editorial, trustworthy, and specific — "
    "never as generic AI promo clutter."
)


class AtelierStrategy:
    """Duck-typed PromptStrategy implementation (see core/protocols.py:97)."""

    # ── Copy: Meta platform copy ─────────────────────────────────────────────

    def build_meta_copy_system(self, context: dict) -> str:
        persona = context.get("persona_info") or ""
        strategy = context.get("creative_strategy") or ""
        persona_block = f"\nTarget Persona:\n{persona}\n" if persona else ""
        strategy_block = f"\nCreative Strategy:\n{strategy}\n" if strategy else ""
        return f"""You are a senior Meta Ads specialist for premium Indian real estate.
You write copy for Facebook and Instagram ad units (the text around the creative).
{persona_block}{strategy_block}
Copy law: the headline sells an EMOTION; supporting text states the fact the way a
friend would say it — casual, specific, no brochure language.

Copy Sections:
1. primary_text: EXACTLY 4 variations. Engaging, value-led. Max 125 characters.
2. headline: EXACTLY 4 variations. Punchy, benefit-led. Max 40 characters.
3. description: EXACTLY 4 variations. Extra detail or social proof. Max 25 characters.
4. call_to_action: single value from this list ONLY (use the Value exactly):
   LEARN_MORE | SIGN_UP | SUBSCRIBE | GET_QUOTE | APPLY_NOW | DOWNLOAD | GET_OFFER | BOOK_NOW

Rules:
- NEVER include placeholder text like [Project Name].
- NEVER include RERA numbers, registration codes, or any regulatory reference.
- Premium, trustworthy tone. No emojis. No "luxury" for sub-₹5Cr projects.
- Each of the 4 variations takes a distinct angle (emotional, logical, urgency, curiosity).
- CRITICAL: respect the character limits.

Return ONLY valid JSON, no markdown. Text fields MUST be lists of exactly 4 strings:
{{
  "primary_text": ["...", "...", "...", "..."],
  "headline": ["...", "...", "...", "..."],
  "description": ["...", "...", "...", "..."],
  "call_to_action": "..."
}}"""

    # ── Copy: on-image ad copy (strict AdCopy JSON contract) ────────────────

    def build_copy_system_prompt(self, context: dict) -> str:
        persona = context.get("persona_info") or ""
        strategy = context.get("creative_strategy") or ""
        instructions = context.get("instructions") or ""
        persona_block = f"\nTarget Persona:\n{persona}\n" if persona else ""
        strategy_block = f"\nCreative Strategy:\n{strategy}\n" if strategy else ""
        instructions_block = (
            f"\nMANDATORY Additional Instructions (override defaults where they conflict):\n{instructions}\n"
            if instructions else ""
        )
        return f"""You are the head copywriter at a premium real-estate creative studio.
You write the words that appear ON the ad image itself.
{persona_block}{strategy_block}{instructions_block}
Copy law:
- headline: max 8 words. It sells an EMOTION — the feeling of living there — never a spec.
- body_copy: max 10 words. The facts, told like a friend would: config, price, location,
  pipe-separated (e.g. "3 BHK | ₹1.57 Cr | Bannerghatta Road"). Every variation carries
  ALL of config, price, and location — never drop one to emphasise an angle.
- NEVER include RERA numbers, registration codes, or any regulatory reference in any field.
- Never explain or pitch didactically — restraint beats explanation.
- cta: EXACTLY one of these labels (verbatim):
    Learn More | Sign Up | Subscribe | Get Quote | Apply Now | Book Now | Download | Get Offer

If Meta ad copy is provided in the brief, derive the 4 variations from those Meta
variations — distill each to a punchy on-image headline, keep the same creative angle.

Generate EXACTLY 4 variations of (headline, body_copy, visual_hint) for 4 images.
visual_hint: one sentence of visual direction (lighting mood, emphasis, atmosphere),
distinct per variation, aligned with its angle.

Return ONLY valid JSON, no markdown:
{{
  "headline": "...",
  "body_copy": "...",
  "cta": "...",
  "variations": [
    {{ "headline": "...", "body_copy": "...", "visual_hint": "..." }},
    {{ "headline": "...", "body_copy": "...", "visual_hint": "..." }},
    {{ "headline": "...", "body_copy": "...", "visual_hint": "..." }},
    {{ "headline": "...", "body_copy": "...", "visual_hint": "..." }}
  ]
}}"""

    def build_copy_user_brief(self, context: dict) -> str:
        lines = [f"Project: {context.get('product_name', '')}"]
        if context.get("description"):
            lines.append(str(context["description"]))
        if context.get("has_product_images"):
            lines.append("Project images attached — the property is the hero visual.")
        if context.get("has_logo_images"):
            lines.append("Brand logo image attached — the official developer logo.")

        brand = context.get("brand_info") or {}
        brand_bits = []
        if brand.get("company_name"):
            brand_bits.append(f"  Company: {brand['company_name']}")
        if brand.get("tagline"):
            brand_bits.append(f"  Tagline: {brand['tagline']}")
        if brand.get("brand_voice"):
            brand_bits.append(f"  Brand voice: {brand['brand_voice']}")
        if brand.get("industry"):
            brand_bits.append(f"  Industry: {brand['industry']}")
        if brand.get("target_personas"):
            brand_bits.append(f"  Target personas: {'; '.join(brand['target_personas'])}")
        if brand_bits:
            lines.append("\nBrand context:\n" + "\n".join(brand_bits))

        lines.append(f"\nAd format: {context.get('ad_format', '1080x1080')}")
        if context.get("persona_info"):
            lines.append(f"\nTarget persona: {context['persona_info']}")
        if context.get("creative_strategy"):
            lines.append(f"\nCreative strategy: {context['creative_strategy']}")
        if context.get("instructions"):
            lines.append(f"\nAdditional user instructions: {context['instructions']}")

        meta = context.get("meta_ad_copy") or {}
        headlines = meta.get("headline") or []
        primaries = meta.get("primary_text") or []
        if headlines or primaries:
            lines.append("\n=== APPROVED META AD COPY ===")
            lines.append("Use these Meta variations as source material for the image copy.")
            for i in range(4):
                h = headlines[i] if i < len(headlines) else ""
                p = primaries[i] if i < len(primaries) else ""
                lines.append(f"\nVariation {i + 1}:\n  Meta Headline: {h}\n  Meta Primary Text: {p}")

        return "\n".join(lines)

    # ── Format selection + blueprint assembly ───────────────────────────────

    def build_image_prompt_system(self, context: dict) -> str:
        menu = format_menu(min_relevance=MIN_FORMAT_RELEVANCE)
        return f"""{_SYSTEM_IDENTITY}

Below is your studio's FORMAT LIBRARY. Each format is a proven Meta ad layout:
an id, when to use it, a worded layout blueprint, and its negatives.

=== FORMAT LIBRARY ===

{menu}

=== END FORMAT LIBRARY ===

Task: read the project brief, then:
1. Choose EXACTLY ONE format — the strongest fit for this project's angle, audience,
   and campaign moment (match against each format's use_when tags and blueprint).
2. Write the final image-generation blueprint for this specific project:
   - Start from the chosen format's blueprint and keep its layout grammar intact —
     zones, splits, and typography hierarchy are authoritative.
   - Make it concrete for THIS project: the property is the hero subject; name the
     scene (facade at dusk, balcony over greens, clubhouse interior…) from the brief.
   - Color: derive the palette from the attached project images; where the format
     names a tonal treatment (dark bg, warm canvas), keep it and harmonise around
     the project's colors. Do not invent brand colors.
   - End with a "Do not:" paragraph merging the format's negatives with premium
     real-estate discipline (no starbursts or discount clutter unless the format
     demands them, no cartoon people, no invented text).

Output contract (strict):
- First line: [format: <chosen_format_id>]
- Then a blank line, then ONLY the final blueprint text. No commentary, no
  mention of the library or the other formats, no markdown headings."""

    def build_image_prompt_brief(self, context: dict) -> str:
        # Same project facts as the copy brief, minus the Meta-copy block.
        lines = [f"Project: {context.get('product_name', '')}"]
        if context.get("description"):
            lines.append(str(context["description"]))
        lines.append(f"\nAd format: {context.get('ad_format', '1080x1080')}")
        if context.get("has_product_images"):
            lines.append("Project images are attached and will condition the generation.")
        else:
            lines.append("No project images attached — the scene comes from the description alone.")
        if context.get("has_logo_images"):
            lines.append("Official developer logo image is attached.")
        if context.get("persona_info"):
            lines.append(f"\nTarget persona: {context['persona_info']}")
        if context.get("creative_strategy"):
            lines.append(f"\nCreative strategy: {context['creative_strategy']}")
        if context.get("instructions"):
            lines.append(f"\nAdditional user instructions: {context['instructions']}")
        return "\n".join(lines)

    # ── Image generation ─────────────────────────────────────────────────────

    def build_image_gen_system(self, context: dict) -> str:
        if context.get("has_logo_images"):
            logo_rule = (
                "A brand logo image is provided — reproduce it EXACTLY as shown: "
                "colours, proportions, typography. Never redraw or restyle it."
            )
        else:
            logo_rule = (
                "No logo image is provided. Identify the developer from the project "
                "name and description and render their authentic logo accurately as "
                "publicly known. If the developer cannot be confidently identified, "
                "omit the logo entirely rather than inventing one."
            )
        return f"""{_SYSTEM_IDENTITY}

You receive project images, a layout blueprint, and approved copy. Generate the
finished static ad as a single image.

IMAGE ROLES:
- Project images are the ONLY source for the hero subject, architecture, environment,
  and palette. Keep the architecture faithful to the renders — never redesign the building.
- LOGO RULE: {logo_rule}

LAYOUT RULE: the blueprint in the prompt is authoritative — its zones, splits, and
typography hierarchy override any default composition instinct.

TEXT RULES:
- Render ONLY the text supplied in the prompt's copy block — never invent prices,
  URLs, phone numbers, RERA numbers, project names, or taglines.
- Every data point (price, configuration, location, possession) appears exactly once
  across the ad. Never repeat a detail.
- Typography must be clean and legible: real glyphs, correct spelling, consistent
  kerning. No garbled, warped, or pseudo-text anywhere.

QUALITY BAR: photorealistic architecture, editorial art direction, premium restraint.
No AI-render tells (impossible geometry, melted details, over-saturated HDR skies)."""

    def build_image_gen_prompt(self, base_prompt: str, ad_copy, variation_index: int) -> str:
        format_id, blueprint = self.split_format_marker(base_prompt)

        hints = self.variation_hints()
        if ad_copy and getattr(ad_copy, "variations", None):
            variations = ad_copy.variations
            var = variations[variation_index % len(variations)]
            visual_hint = (getattr(var, "visual_hint", "") or "").strip()
            hint = visual_hint if visual_hint else hints[variation_index % len(hints)]
            copy_block = (
                "\n\nCopy for this variation (render verbatim on the image):\n"
                f'  Headline: "{var.headline}"\n'
                f'  Body copy: "{var.body_copy}"\n'
                f'  CTA: "{ad_copy.cta}"'
            )
        else:
            hint = hints[variation_index % len(hints)] if hints else ""
            copy_block = ""

        hint_block = f"\n\nVariation direction: {hint}" if hint else ""
        return f"{blueprint}{copy_block}{hint_block}"

    def variation_hints(self) -> list[str]:
        return [
            "Golden-hour dusk: warm low sun on the facade, long shadows, glowing interiors.",
            "Blue-hour architectural: deep twilight sky, crisp building lights, calm and premium.",
            "Morning clarity: soft daylight, fresh greens around the property, airy and open.",
            "Lived-in warmth: balcony or amenity moment, warm interior light, quiet human presence.",
        ]

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def split_format_marker(base_prompt: str):
        """Return (format_id | None, prompt without the marker line)."""
        match = _FORMAT_MARKER.match(base_prompt or "")
        if not match:
            return None, (base_prompt or "").strip()
        return match.group("id"), base_prompt[match.end():].strip()
