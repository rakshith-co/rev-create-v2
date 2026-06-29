import asyncio
import io
import logging
import os
import re
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image
from google import genai
from google.genai import types

logger = logging.getLogger("revCreate.image_search")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MIN_DIMENSION = 400  # ignore images smaller than this on either side

# Matches direct image URLs (with extension)
_IMAGE_URL_RE = re.compile(
    r'https?://[^\s<>"\')\]]+\.(?:jpg|jpeg|png|webp)(?:\?[^\s<>"\')\]]*)?',
    re.IGNORECASE,
)
# Matches any plain https URL (fallback text parsing)
_ANY_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+', re.IGNORECASE)

# img src / all common lazy-load data attributes
_IMG_SRC_RE = re.compile(
    r'<img[^>]+(?:src|data-src|data-lazy|data-lazy-src|data-original|data-url)\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
# srcset attribute (pick largest from comma-separated list)
_SRCSET_RE = re.compile(r'srcset\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
# CSS background-image: url(...)
_BG_IMAGE_RE = re.compile(
    r'background(?:-image)?\s*:\s*url\(["\']?(https?://[^"\')\s]+)["\']?\)',
    re.IGNORECASE,
)
# og:image meta tag
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)\s*=\s*["\']og:image["\'][^>]+content\s*=\s*["\']([^"\']+)["\']'
    r'|<meta[^>]+content\s*=\s*["\']([^"\']+)["\'][^>]+(?:property|name)\s*=\s*["\']og:image["\']',
    re.IGNORECASE,
)
# Skip obviously non-product image URLs (icons, tracking pixels, UI assets, logos, thumbnails)
_SKIP_URL_RE = re.compile(
    r'(?:logo|icon|pixel|tracking|spacer|avatar|1x1|beacon|\.gif'
    r'|/assets/|/static/|/dist/|/build/|/public/img/ui'
    r'|vertexaisearch\.cloud\.google\.com'
    r'|cropped-'           # WordPress logo crops
    r'|-\d+x\d+\.)',       # WordPress thumbnail sizes like -300x138.webp
    re.IGNORECASE,
)


async def _search_page_urls(
    product_name: str,
    description: str,
    persona_info: str = "",
    creative_strategy: str = "",
) -> list[str]:
    """Step 1: Use Gemini grounding to find pages that host product images."""
    client = genai.Client(api_key=GEMINI_API_KEY)

    persona_line = f"Target audience: {persona_info}\n" if persona_info else ""
    strategy_line = f"Creative strategy: {creative_strategy}\n" if creative_strategy else ""

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=(
            f'Product name: "{product_name}"\n'
            f"Description: {description}\n"
            f"{persona_line}{strategy_line}"
            f"Instructions:\n"
            f"1. Extract the specific location from the description (city, neighbourhood, locality). "
            f"If no location is mentioned, use just the product name.\n"
            f"2. Search Google for the official website, photo gallery pages, and news/media pages "
            f"for '{product_name}' at the extracted location.\n"
            f"3. Return the URLs of 3 to 5 web pages that are most likely to have photographs "
            f"of this specific property — prefer official developer pages, gallery sections, "
            f"and real-estate listing sites.\n"
            f"Return only the URLs, one per line, nothing else."
        ),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    logger.info("Page search — product=%r description=%r", product_name, description[:200])

    # Prefer grounding_metadata source URLs — these are the real destination URLs,
    # not the vertexaisearch.cloud.google.com/grounding-api-redirect/... wrappers
    # that Gemini embeds in response.text.
    page_urls: list[str] = []
    try:
        for candidate in response.candidates or []:
            meta = getattr(candidate, "grounding_metadata", None)
            if not meta:
                continue
            for chunk in getattr(meta, "grounding_chunks", None) or []:
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None) if web else None
                if uri and uri not in page_urls:
                    page_urls.append(uri)
    except Exception as e:
        logger.debug("Failed to read grounding_metadata: %s", e)

    # Fall back to regex parsing of response text if grounding_metadata was empty
    if not page_urls:
        logger.debug("grounding_metadata empty — falling back to text URL parsing")
        text = response.text or ""
        logger.info("Gemini page search raw response:\n%s", text[:1000])
        seen: set[str] = set()
        for u in _ANY_URL_RE.findall(text):
            if u not in seen:
                seen.add(u)
                page_urls.append(u)

    logger.info("Page URLs found (%d): %s", len(page_urls), page_urls)
    return page_urls[:5]


async def _extract_images_from_page(page_url: str) -> list[str]:
    """Step 2: Fetch a page and extract candidate image URLs from HTML."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(page_url, timeout=10.0, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            r.raise_for_status()
            html = r.text
            final_url = str(r.url)
    except Exception as e:
        logger.debug("Failed to fetch page %s: %s", page_url, e)
        return []

    base = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
    candidates: list[str] = []

    def _abs(url: str) -> str:
        return url if url.startswith("http") else urljoin(base, url)

    # og:image first (usually the best hero image)
    for m in _OG_IMAGE_RE.finditer(html):
        url = m.group(1) or m.group(2)
        if url:
            candidates.append(_abs(url))

    # img src / data-src / lazy-load attributes
    for m in _IMG_SRC_RE.finditer(html):
        url = m.group(1)
        if url and not url.startswith("data:"):
            candidates.append(_abs(url))

    # srcset — pick the last (largest) entry from each srcset value
    for m in _SRCSET_RE.finditer(html):
        for entry in m.group(1).split(","):
            parts = entry.strip().split()
            if parts:
                candidates.append(_abs(parts[0]))

    # CSS background-image
    for m in _BG_IMAGE_RE.finditer(html):
        candidates.append(m.group(1))

    # Direct image URLs anywhere in the raw HTML
    candidates += _IMAGE_URL_RE.findall(html)

    # Deduplicate and filter noise
    seen: set[str] = set()
    filtered: list[str] = []
    for u in candidates:
        if u not in seen and not _SKIP_URL_RE.search(u):
            seen.add(u)
            filtered.append(u)

    # Prefer same-domain images (more likely to be actual product photos, not framework assets)
    page_host = urlparse(page_url).netloc
    same_domain = [u for u in filtered if urlparse(u).netloc == page_host]
    other = [u for u in filtered if urlparse(u).netloc != page_host]
    ordered = same_domain + other

    logger.debug("Extracted %d image candidates from %s (%d same-domain)", len(ordered), page_url, len(same_domain))
    return ordered[:15]


async def _download_image(url: str) -> tuple[bytes, str, int] | None:
    """Download and validate an image. Returns (bytes, content_type, area) or None."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(url, timeout=8.0, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            content_type = r.headers.get("content-type", "").split(";")[0].strip()
            if content_type not in _ALLOWED_TYPES:
                return None
            img = Image.open(io.BytesIO(r.content))
            w, h = img.size
            if w < _MIN_DIMENSION or h < _MIN_DIMENSION:
                logger.debug("Skipping small image %dx%d — %s", w, h, url)
                return None
            return r.content, content_type, w * h
    except Exception as e:
        logger.debug("Failed to download %s: %s", url, e)
        return None


async def _pick_best_with_ad_copy(
    candidates: list[tuple[bytes, str]],
    ad_copy_text: str,
) -> int:
    client = genai.Client(api_key=GEMINI_API_KEY)
    contents: list = [
        f"You are selecting the best product photo to use as the hero visual in an ad.\n"
        f"The ad has the following copy:\n\n{ad_copy_text}\n\n"
        f"Choose which of the {len(candidates)} candidate images best serves as the "
        f"hero/background visual for this specific ad — consider how well the image "
        f"conveys the product, mood, and message of the copy above.\n"
        f"Reply with ONLY the index number (1-based), nothing else.\n\nCandidate images:",
    ]
    for i, (img_bytes, mime_type) in enumerate(candidates):
        contents.append(f"Image {i + 1}:")
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=contents,
    )
    try:
        idx = int(response.text.strip()) - 1
        return max(0, min(idx, len(candidates) - 1))
    except Exception:
        return 0


async def pick_best_product_image(
    candidates: list[tuple[bytes, str]],
    ad_copy_text: str,
) -> tuple[bytes, str]:
    """From a list of provided product images, pick the one that best matches the ad copy."""
    if len(candidates) == 1:
        return candidates[0]
    try:
        idx = await _pick_best_with_ad_copy(candidates, ad_copy_text)
    except Exception as e:
        logger.warning("Best-pick failed (%s) — using first candidate", e)
        idx = 0
    logger.info("Product image selected — index=%d/%d", idx + 1, len(candidates))
    return candidates[idx]


async def search_and_fetch_product_image(
    product_name: str,
    description: str,
    ad_copy_text: str,
    persona_info: str = "",
    creative_strategy: str = "",
) -> tuple[bytes, str] | None:
    """Search the web for a product image.

    Step 1: Gemini grounding finds pages that host product photos.
    Step 2: We scrape those pages for actual image URLs and download the best one.
    Returns None if nothing downloadable is found.
    """
    try:
        page_urls = await _search_page_urls(product_name, description, persona_info, creative_strategy)
        if not page_urls:
            logger.warning("Gemini found no pages for %r", product_name)
            return None

        # Scrape all pages concurrently for image URL candidates
        per_page = await asyncio.gather(*[_extract_images_from_page(u) for u in page_urls])
        image_urls: list[str] = []
        seen: set[str] = set()
        for urls in per_page:
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    image_urls.append(u)

        if not image_urls:
            logger.warning("No image URLs found in scraped pages for %r", product_name)
            return None

        logger.info("Total image candidates after scraping: %d", len(image_urls))

        # Download up to 8 concurrently; _download_image filters by min dimension
        downloads = await asyncio.gather(*[_download_image(u) for u in image_urls[:8]])
        # Each result is (bytes, content_type, area) — sort largest-first, no LLM needed
        candidates = [
            (img, ctype, area, url)
            for (result, url) in zip(downloads, image_urls[:8])
            if result is not None
            for (img, ctype, area) in [result]
        ]
        candidates.sort(key=lambda x: x[2], reverse=True)

        if not candidates:
            logger.warning("All candidate image downloads failed for %r", product_name)
            return None

        img, ctype, area, url = candidates[0]
        logger.info("Web image selected — area=%dpx url=%s", area, url)
        return img, ctype

    except Exception as e:
        logger.error("Web image search failed: %s", e)
        return None
