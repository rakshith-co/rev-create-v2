import json
import logging
import os

from google import genai
from google.genai import types

logger = logging.getLogger("revCreate.brand")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
COPY_MODEL = "gemini-2.5-flash"

_EXTRACTION_SCHEMA = """{
  "company_name": "string",
  "tagline": "string or null",
  "brand_voice": "string (e.g. luxury, playful, professional, bold, minimalist)",
  "target_personas": ["string", "..."],
  "industry": "string"
}"""

_UNKNOWN_VALUES = {"unknown", "n/a", "", "not specified", "not mentioned", "unclear"}


async def extract_brand_info(product_name: str, description: str) -> dict:
    """Extract brand details and target personas from the project description.

    If the description lacks brand information (e.g. company name is missing),
    a second call with Google Search grounding is made to supplement.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""Extract brand information from these product details. Return ONLY valid JSON.

Product name: {product_name}
Description: {description}

Return this exact JSON structure:
{_EXTRACTION_SCHEMA}

Rules:
- target_personas: 1-3 specific audience segments (age, interest, context)
- brand_voice: single adjective or short phrase
- If a field cannot be determined from the description, set it to null (strings) or [] (arrays)"""

    try:
        response = await client.aio.models.generate_content(
            model=COPY_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        data = json.loads(response.text.strip())
    except Exception as e:
        logger.warning("Brand extraction failed — %s", e)
        return _defaults(product_name)

    company = (data.get("company_name") or "").strip().lower()
    if company in _UNKNOWN_VALUES:
        logger.info("Brand extraction incomplete — attempting web supplement for %r", product_name)
        data = await _web_supplement(client, product_name, description, data)

    logger.info(
        "Brand info — company=%r voice=%r personas=%d",
        data.get("company_name"), data.get("brand_voice"), len(data.get("target_personas") or []),
    )
    return data


async def _web_supplement(client, product_name: str, description: str, partial: dict) -> dict:
    """Use Google Search grounding to fill in missing brand details."""
    try:
        search_prompt = f"""Search for brand information about "{product_name}".
Context: {description[:400]}

Find the company name, brand tone/voice, target audience, and industry.
Return ONLY valid JSON:
{_EXTRACTION_SCHEMA}"""

        response = await client.aio.models.generate_content(
            model=COPY_MODEL,
            contents=search_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = response.text or ""
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end > start:
            web_data = json.loads(text[start:end])
            for key, val in web_data.items():
                existing = partial.get(key)
                if not existing or (isinstance(existing, str) and existing.lower() in _UNKNOWN_VALUES):
                    partial[key] = val
    except Exception as e:
        logger.warning("Web supplement failed — %s", e)

    return partial


def _defaults(product_name: str) -> dict:
    return {
        "company_name": product_name,
        "tagline": None,
        "brand_voice": "professional",
        "target_personas": [],
        "industry": "general",
    }
