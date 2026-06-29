import os
import base64
import logging
from google import genai
from google.genai import types

logger = logging.getLogger("revCreate.image_model")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# "gemini-3-pro-image-preview"  # gemini-3.1-flash-image-preview
IMAGE_MODEL = "gemini-3-pro-image-preview"

_SUPPORTED_RATIOS = [
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4",
    "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
]


def _dimensions_to_aspect_ratio(ad_format: str) -> str:
    """Convert 'WxH' string to the closest supported aspect ratio."""
    try:
        w, h = ad_format.lower().split("x")
        ratio = int(w.strip()) / int(h.strip())
    except Exception:
        return "1:1"

    def _ratio_val(r: str) -> float:
        a, b = r.split(":")
        return int(a) / int(b)

    return min(_SUPPORTED_RATIOS, key=lambda r: abs(_ratio_val(r) - ratio))


async def generate_image(
    prompt: str,
    ad_format: str = "1080x1080",
    aspect_ratio: str | None = None,
    product_images: list[tuple[bytes, str]] | None = None,
    ref_images: list[tuple[bytes, str]] | None = None,
    logo_images: list[tuple[bytes, str]] | None = None,
    source_ad: tuple[bytes, str] | None = None,
    system_prompt: str | None = None,
    description: str = "",
    persona_info: str = "",
    creative_strategy: str = "",
    meta_ad_copy: dict | None = None,
    ad_copy: dict | None = None,
    temperature: float = 0.9,
) -> dict:
    """Generate an image using the Gemini image generation model.

    ref_images (reference ads) are passed first so the model uses them as a
    structural template. product_images follow so the model uses the product
    as the hero visual. The text prompt comes last.

    aspect_ratio: explicit Gemini aspect ratio string (e.g. "9:16"). When
    provided it bypasses _dimensions_to_aspect_ratio. Always pass this for
    size variants to avoid nearest-match approximation producing wrong ratios.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    aspect_ratio = aspect_ratio or _dimensions_to_aspect_ratio(ad_format)
    logger.info(
        "Requesting image — model=%s aspect_ratio=%s source_ad=%s ref_images=%d product_images=%d",
        IMAGE_MODEL,
        aspect_ratio,
        source_ad is not None,
        len(ref_images) if ref_images else 0,
        len(product_images) if product_images else 0,
    )

    contents: list = []

    # ── Context Brief ────────────────────────────────────────────────────────
    context_lines = []
    if description:
        context_lines.append(f"Product Description: {description}")
    if persona_info:
        context_lines.append(f"Target Persona: {persona_info}")
    if creative_strategy:
        context_lines.append(f"Creative Strategy: {creative_strategy}")

    if ad_copy:
        context_lines.append("Rendered Ad Copy (On Image):")
        if ad_copy.get("headline"):
            context_lines.append(f"  Headline: {ad_copy['headline']}")
        if ad_copy.get("body_copy"):
            context_lines.append(f"  Body Copy: {ad_copy['body_copy']}")
        if ad_copy.get("cta"):
            context_lines.append(f"  CTA: {ad_copy['cta']}")

    if meta_ad_copy:
        context_lines.append("Meta Ad Copy:")
        if "headline" in meta_ad_copy:
            h = meta_ad_copy["headline"]
            h_str = h[0] if isinstance(h, list) and h else h
            context_lines.append(f"  Headline: {h_str}")
        if "primary_text" in meta_ad_copy:
            p = meta_ad_copy["primary_text"]
            p_str = p[0] if isinstance(p, list) and p else p
            context_lines.append(f"  Primary Text: {p_str}")

    if context_lines:
        contents.append("=== CONTEXT FOUNDATION ===\n" + "\n".join(context_lines))

    # ── Turn 1: Establish Layout Context ─────────────────────────────────────
    # Source ad goes first when adapting an existing ad to a new size/placement.
    if source_ad:
        contents.append(
            "=== SOURCE AD — the fully rendered ad to adapt for this placement ===\n"
            "Preserve ALL of the following from this ad exactly:\n"
            "  • Overall composition, zone positions, and layout structure\n"
            "  • All graphic elements: dividers, panels, badges, borders, shapes, curves\n"
            "  • Typography: font weight hierarchy, size ratios, case treatment, letter spacing\n"
            "  • Colour palette: background, text, overlay, strip, and button colours\n"
            "  • Brand elements: logo position and size, CTA design\n"
            "  • Ad copy: headline, body copy, and CTA text — do not alter any wording\n"
            "  • Hero visual and background — the product shown in this ad MUST remain the hero/background.\n"
            "    Use the PRODUCT IMAGES provided to faithfully reconstruct the product at the new canvas size.\n"
            "Only change the canvas aspect ratio and recompose zones to fit the new dimensions naturally."
        )
        img_bytes, mime_type = source_ad
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

    # Reference ad (Type B) establishes the layout wireframe.
    if ref_images:
        contents.append(
            "=== IMAGE TYPE B: REFERENCE AD — LAYOUT WIREFRAME ONLY ===\n"
            "MANDATORY: Use this image ONLY as a template for layout structure and zones.\n"
            "Replicate the following EXACTLY from this reference ad:\n"
            "  ✓ Zone positions — logo, headline, body copy, CTA: exact corner, side, and vertical placement\n"
            "  ✓ Panel structure — split-panel proportions, solid colour blocks, full-bleed regions\n"
            "  ✓ Graphic elements — dividers/rules, geometric shapes, badges, borders, curves, and their colours\n"
            "  ✓ Typography hierarchy — weight, size ratio, case treatment, letter spacing, and alignment per text level\n"
            "  ✓ Colour palette — background, text, overlay, strip, and button colours\n"
            "  ✓ Overlay / tint — colour, opacity, and blend mode applied over the background image\n"
            "  ✓ Spacing rhythm — outer margins, inter-element gaps, strip heights\n"
            "FORBIDDEN: Do NOT use any visual content from this image.\n"
            "  → Background scene / environment → DISCARD COMPLETELY\n"
            "  → Hero visual / building / product shown → DISCARD COMPLETELY\n"
            "  → Logo / brand marks → DISCARD COMPLETELY\n"
            "BOTTOM-ZONE OVERRIDE (absolute — supersedes any layout in this reference ad):\n"
            "  The bottom 20% of your output must be a seamless continuation of the hero background scene.\n"
            "  No text, no graphics, no icons, no strips, no overlays, and NO separate or different image placed there.\n"
            "  The full canvas must look like a single unified photograph — never a collage or stacked layout."
        )
        for img_bytes, mime_type in ref_images:
            contents.append(types.Part.from_bytes(
                data=img_bytes, mime_type=mime_type))

    # ── Turn 2: Provide Visual Content ───────────────────────────────────────
    # Product images (Type A) provide the actual content to fill the layout.
    if product_images:
        if source_ad:
            # Size-variant mode: source_ad is the layout authority.
            # Product images are a supplementary visual reference only.
            contents.append(
                "=== PRODUCT IMAGES — SUPPLEMENTARY VISUAL REFERENCE ===\n"
                "These are provided for visual context only. The SOURCE AD above is the layout authority.\n"
                "Use these only to fill or reconstruct visual areas (hero, background) that cannot be\n"
                "faithfully reproduced from the source ad at the new canvas size.\n"
                "Do NOT override any composition, colour, or typography decisions from the source ad."
            )
        else:
            # Original generation mode: product images are the primary visual source.
            contents.append(
                "=== IMAGE TYPE A: PRODUCT IMAGES — PRIMARY VISUAL SOURCE ===\n"
                "MANDATORY: Every visual element in the final ad MUST be sourced from these images.\n"
                "Fill the layout provided by the Reference Ad (Type B) using ONLY these images for:\n"
                "  • Background scene, sky, environment, and landscape\n"
                "  • Hero visual (the main subject of the ad)\n"
                "  • Brand logo — reproduce EXACTLY as it appears here\n"
                "  • Colour palette\n"
                "These images define 100% of the visual content. You MUST replace all visuals from Type B with these."
            )
        for img_bytes, mime_type in product_images:
            contents.append(types.Part.from_bytes(
                data=img_bytes, mime_type=mime_type))

    if logo_images:
        logo_override = "Type A or Type B images" if ref_images else "product images"
        contents.append(
            "=== IMAGE TYPE C: BRAND LOGO — PIXEL-PERFECT REPRODUCTION ===\n"
            "This is the OFFICIAL brand logo. It is the authoritative source. Rules:\n"
            "  • Reproduce it PIXEL-PERFECT — do NOT alter any of: colours, hues, gradients, proportions,\n"
            "    letterforms, icon shapes, spacing, or any other visual property\n"
            "  • Treat this logo as a locked asset — render it as-is, no reinterpretation\n"
            "  • Place it in the appropriate brand corner of the ad (top-left or top-right)\n"
            f"  • NEVER use any logo from {logo_override} when this Type C logo is provided\n"
            "  • NEVER invent, stylise, or 'improve' this logo in any way"
        )
        for img_bytes, mime_type in logo_images:
            contents.append(types.Part.from_bytes(
                data=img_bytes, mime_type=mime_type))
    contents.append(prompt)

    response = await client.aio.models.generate_content(
        model=IMAGE_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            temperature=temperature,
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size="1K",
            ),
        ),
    )

    u = response.usage_metadata
    logger.info(
        "TOKENS image_gen — input=%s output=%s total=%s aspect=%s",
        u.prompt_token_count,
        u.candidates_token_count,
        u.total_token_count,
        aspect_ratio,
    )
    logger.info("Gemini response — candidates=%d",
                len(response.candidates or []))
    for i, part in enumerate(response.parts):
        if part.text is not None:
            logger.info("  part[%d] text: %r", i, part.text[:200])
        elif part.inline_data is not None:
            logger.info(
                "  part[%d] image: mime=%s size=%.1fKB",
                i, part.inline_data.mime_type, len(
                    part.inline_data.data) / 1024,
            )
        else:
            logger.info("  part[%d] unknown: %s", i, part)

    for part in response.parts:
        if part.inline_data is not None:
            return {
                "image_base64": base64.b64encode(part.inline_data.data).decode(),
                "input_tokens": u.prompt_token_count,
                "output_tokens": u.candidates_token_count,
            }

    logger.error("No image part in Gemini response — parts=%d", len(response.parts))
    raise ValueError("Gemini response contained no image part")


async def generate_logo_image(
    product_images: list[tuple[bytes, str]] | None = None,
    description: str = "",
    brand_info: dict | None = None,
) -> tuple[bytes, str] | None:
    """Extract/render the brand logo from product images, or generate from brand info alone.

    Returns (logo_bytes, mime_type) or None if generation fails.
    Called once before the 4 variation renders so all variants share the same logo.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)

    company = (brand_info or {}).get("company_name", "")
    tagline = (brand_info or {}).get("tagline", "")
    industry = (brand_info or {}).get("industry", "")
    brand_hint = f" for {company}" if company else ""

    contents: list = []

    if product_images:
        contents.append(
            "The following images are provided. They may contain the brand logo."
        )
        for img_bytes, mime_type in product_images:
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

        if description:
            contents.append(f"Product description: {description}")

        contents.append(
            f"Task: Extract and reproduce the brand logo{brand_hint} as a clean standalone image.\n"
            "Output ONLY the logo on a plain white background.\n"
            "Rules:\n"
            "  • Reproduce every colour, shape, letterform, and proportion EXACTLY as it appears in the source\n"
            "  • No background imagery, no ad elements, no text other than the logo itself\n"
            "  • If no logo is identifiable in the source images, render a clean text wordmark from the company name\n"
            "  • Do NOT add effects, gradients, or styling not present in the original"
        )
    else:
        # Text-only path: generate a logo purely from brand information
        brand_context_lines = []
        if company:
            brand_context_lines.append(f"Company name: {company}")
        if industry:
            brand_context_lines.append(f"Industry: {industry}")
        if tagline:
            brand_context_lines.append(f"Tagline: {tagline}")
        if description:
            brand_context_lines.append(f"Description: {description}")

        brand_context = "\n".join(brand_context_lines) if brand_context_lines else "Unknown brand"

        contents.append(
            f"Task: Design a professional brand logo{brand_hint}.\n\n"
            f"Brand information:\n{brand_context}\n\n"
            "Output ONLY the logo on a plain white background.\n"
            "Rules:\n"
            "  • Create a clean, professional wordmark or logomark that suits the brand\n"
            "  • For real estate / property developers: use premium, trustworthy typography and a restrained colour palette\n"
            "  • No background imagery, no taglines, no decorative elements beyond the logo itself\n"
            "  • The company name must be legible and prominently rendered\n"
            "  • Keep it minimal — avoid clip-art, gradients, or over-styled effects"
        )
        logger.info("Generating logo from brand info (no product images) — company=%r", company)

    try:
        response = await client.aio.models.generate_content(
            model=IMAGE_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(aspect_ratio="1:1", image_size="1K"),
            ),
        )
        for part in response.parts:
            if part.inline_data is not None:
                logger.info("Logo pre-generated — size=%.1fKB", len(part.inline_data.data) / 1024)
                return (part.inline_data.data, part.inline_data.mime_type or "image/png")
        logger.warning("Logo pre-generation returned no image part")
    except Exception as e:
        logger.warning("Logo pre-generation failed — %s", e)

    return None


_EDIT_SYSTEM_PROMPT = (
    "You are an expert ad creative editor. "
    "You receive an ad creative image along with product description, ad copy, target audience, and creative strategy context. "
    "Apply each edit instruction precisely while preserving brand identity, layout, colour palette, and creative direction. "
    "Only modify what the instruction explicitly requests — leave everything else unchanged."
)


async def edit_image(
    image_bytes: bytes,
    instruction: str,
    persona_info: str = "",
    creative_strategy: str = "",
    edit_history: list[str] | None = None,
    description: str = "",
    meta_ad_copy: dict | None = None,
    ad_copy: dict | None = None,
) -> dict:
    """Edit an existing image via Gemini using a structured multi-turn conversation.

    Conversation structure:
      User:  [persona/strategy brief] + [current image]
      Model: (ack)
      User:  [past instruction 1]       ← oldest
      Model: (ack)
      ...
      User:  [past instruction N]       ← most recent before this edit
      Model: (ack)
      User:  [latest instruction]       ← triggers generation
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info(
        "Editing image — model=%s history=%d instruction=%r",
        IMAGE_MODEL, len(edit_history or []), instruction[:80],
    )

    # ── Turn 1: context brief + current image ────────────────────────────────
    brief_parts = []
    context_lines = []
    if description:
        context_lines.append(f"Product Description: {description}")
    if persona_info:
        context_lines.append(f"Target Persona: {persona_info}")
    if creative_strategy:
        context_lines.append(f"Creative Strategy: {creative_strategy}")
    
    if ad_copy:
        context_lines.append("Rendered Ad Copy (On Image):")
        if ad_copy.get("headline"):
            context_lines.append(f"  Headline: {ad_copy['headline']}")
        if ad_copy.get("body_copy"):
            context_lines.append(f"  Body Copy: {ad_copy['body_copy']}")
        if ad_copy.get("cta"):
            context_lines.append(f"  CTA: {ad_copy['cta']}")

    if meta_ad_copy:
        context_lines.append("Meta Ad Copy:")
        if "headline" in meta_ad_copy:
            h = meta_ad_copy["headline"]
            h_str = h[0] if isinstance(h, list) and h else h
            context_lines.append(f"  Headline: {h_str}")
        if "primary_text" in meta_ad_copy:
            p = meta_ad_copy["primary_text"]
            p_str = p[0] if isinstance(p, list) and p else p
            context_lines.append(f"  Primary Text: {p_str}")

    if context_lines:
        brief_parts.append(types.Part.from_text(text="\n".join(context_lines)))
    brief_parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))

    contents: list = [types.Content(role="user", parts=brief_parts)]

    # ── Interleave past instructions ──────────────────────────────────────────
    for past_instruction in (edit_history or []):
        contents.append(types.Content(role="model", parts=[types.Part.from_text(text="Edit applied.")]))
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=past_instruction)]))

    # ── Close with model ack, then latest instruction ─────────────────────────
    contents.append(types.Content(role="model", parts=[types.Part.from_text(text="Ready for the next edit.")]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=instruction)]))

    response = await client.aio.models.generate_content(
        model=IMAGE_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_EDIT_SYSTEM_PROMPT,
            response_modalities=["TEXT", "IMAGE"],
        ),
    )

    u = response.usage_metadata
    logger.info(
        "TOKENS image_edit — input=%s output=%s total=%s",
        u.prompt_token_count,
        u.candidates_token_count,
        u.total_token_count,
    )
    logger.info("Gemini edit response — candidates=%d",
                len(response.candidates or []))
    for i, part in enumerate(response.parts):
        if part.text is not None:
            logger.info("  part[%d] text: %r", i, part.text[:200])
        elif part.inline_data is not None:
            logger.info(
                "  part[%d] image: mime=%s size=%.1fKB",
                i, part.inline_data.mime_type, len(
                    part.inline_data.data) / 1024,
            )
        else:
            logger.info("  part[%d] unknown: %s", i, part)

    for part in response.parts:
        if part.inline_data is not None:
            return {
                "image_base64": base64.b64encode(part.inline_data.data).decode(),
                "input_tokens": u.prompt_token_count,
                "output_tokens": u.candidates_token_count,
            }

    logger.error("No image part in Gemini edit response")
    raise ValueError("Gemini edit response contained no image part")
