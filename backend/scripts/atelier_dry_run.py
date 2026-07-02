#!/usr/bin/env python3
"""Dry-run the Atelier strategy without any API key, DB, or network.

Prints every prompt the pipeline would send for a sample brief, in pipeline
order. Use it to eyeball prompt assembly after editing formats or the strategy.

Run from backend/:  python -m scripts.atelier_dry_run
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.atelier import AtelierStrategy


class _Var:
    def __init__(self, headline, body_copy, visual_hint=""):
        self.headline, self.body_copy, self.visual_hint = headline, body_copy, visual_hint


class _AdCopy:
    def __init__(self, variations, cta):
        self.variations, self.cta = variations, cta


BRIEF = {
    "product_name": "Godrej Brooklyn Avenue",
    "description": (
        "Premium residences in KPHB, Hyderabad. Brooklyn Neo-Gothic architecture, "
        "3 & 4 BHK from ₹2.1 Cr, 36-storey towers, sky lounges, possession 2028."
    ),
    "ad_format": "1080x1080",
    "has_product_images": True,
    "has_ref_images": False,
    "has_logo_images": True,
    "persona_info": "Karthik, 38, VP Product at an EdTech startup, upgrading for his family.",
    "creative_strategy": "Own the skyline: Brooklyn character architecture as the status signal.",
    "instructions": "",
    "brand_info": {"company_name": "Godrej Properties"},
    "meta_ad_copy": None,
}

# What the copy step would return (sample — live runs get this from the LLM).
SAMPLE_COPY = _AdCopy(
    [_Var("The skyline answers to you", "3 BHK | ₹2.1 Cr | KPHB", "blue-hour tower hero")],
    cta="Book Now",
)


def main() -> None:
    s = AtelierStrategy()
    sections = [
        ("1. META COPY — system", s.build_meta_copy_system(BRIEF)),
        ("2. ON-IMAGE COPY — system", s.build_copy_system_prompt(BRIEF)),
        ("2b. COPY — user brief", s.build_copy_user_brief(BRIEF)),
        ("3. FORMAT SELECT + BLUEPRINT — system", s.build_image_prompt_system(BRIEF)),
        ("3b. FORMAT SELECT — user brief", s.build_image_prompt_brief(BRIEF)),
        ("4. IMAGE GEN — system", s.build_image_gen_system(BRIEF)),
        ("4b. IMAGE GEN — final prompt (sample blueprint + copy, variation 0)",
         s.build_image_gen_prompt(
             "[format: magazine_style_v1]\n\nFull-bleed dusk facade hero, bottom 40% "
             "gradient panel, two-line condensed uppercase headline…",
             SAMPLE_COPY, 0)),
    ]
    for title, body in sections:
        print("=" * 88)
        print(title)
        print("=" * 88)
        print(body)
        print()
    print(f"[dry-run ok] selector menu includes "
          f"{s.build_image_prompt_system(BRIEF).count('### ')} formats")


if __name__ == "__main__":
    main()
