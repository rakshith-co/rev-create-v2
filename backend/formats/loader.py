"""Runtime loader for the ad-format library.

Formats are authored as backend/formats/*.md and compiled to
backend/seeds/formats.json by backend/formats/build.py. This module reads the
compiled JSON and serves it to strategies. Stdlib only — no third-party deps.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("revCreate.formats.loader")

_SEED_PATH = Path(__file__).resolve().parent.parent / "seeds" / "formats.json"

_cache: list[dict] | None = None


def load_formats(refresh: bool = False) -> list[dict]:
    """All format records from the compiled seed, cached after first read."""
    global _cache
    if _cache is None or refresh:
        if not _SEED_PATH.exists():
            raise FileNotFoundError(
                f"{_SEED_PATH} not found — run `python3 backend/formats/build.py` first"
            )
        data = json.loads(_SEED_PATH.read_text())
        _cache = data["formats"]
        logger.info("Loaded %d formats from %s", len(_cache), _SEED_PATH)
    return _cache


def active_formats(min_relevance: int = 0) -> list[dict]:
    """Production-ready formats, optionally filtered by real-estate relevance."""
    return [
        f for f in load_formats()
        if f.get("status") == "active"
        and (f.get("re_relevance") or 0) >= min_relevance
    ]


def get_format(format_id: str) -> dict | None:
    for f in load_formats():
        if f.get("id") == format_id:
            return f
    return None


def format_menu(min_relevance: int = 6) -> str:
    """The format library as a compact text menu for the selector LLM call.

    Ordered by re_relevance descending so the strongest real-estate formats
    lead the menu. Includes the full blueprint + negatives — the selector must
    be able to emit the chosen format's layout without a second lookup.
    """
    formats = sorted(
        active_formats(min_relevance=min_relevance),
        key=lambda f: -(f.get("re_relevance") or 0),
    )
    blocks = []
    for f in formats:
        blocks.append(
            f"### {f['id']} — {f['name']}\n"
            f"use_when: {', '.join(f.get('use_when') or []) or 'general'}\n"
            f"blueprint: {f.get('blueprint', '').strip()}\n"
            f"negatives: {f.get('negatives', '').strip() or 'none'}"
        )
    return "\n\n".join(blocks)
