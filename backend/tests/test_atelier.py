"""Tests for the Atelier strategy + format loader — pure functions, no I/O.

Run from backend/:  python -m pytest tests/test_atelier.py
Or without pytest:  python -m tests.test_atelier
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from formats import loader
from strategies.atelier import AtelierStrategy, MIN_FORMAT_RELEVANCE


# ── duck AdCopy stand-ins (protocol only needs .variations/.cta attributes) ──

class _Var:
    def __init__(self, headline, body_copy, visual_hint=""):
        self.headline = headline
        self.body_copy = body_copy
        self.visual_hint = visual_hint


class _AdCopy:
    def __init__(self, variations, cta="Book Now"):
        self.variations = variations
        self.cta = cta


def _ctx(**overrides):
    base = {
        "product_name": "Godrej Brooklyn Avenue",
        "description": "Premium 3 BHK residences in KPHB, Hyderabad.",
        "ad_format": "1080x1080",
        "has_product_images": True,
        "has_ref_images": False,
        "has_logo_images": True,
        "persona_info": "Karthik, 38, VP Product, upgrading for family",
        "creative_strategy": "Zero-commute schooling angle",
        "instructions": "",
        "brand_info": {"company_name": "Godrej Properties"},
        "meta_ad_copy": None,
    }
    base.update(overrides)
    return base


# ── loader ────────────────────────────────────────────────────────────────────

def test_loader_loads_compiled_seed():
    formats = loader.load_formats(refresh=True)
    assert len(formats) >= 40
    ids = [f["id"] for f in formats]
    assert len(ids) == len(set(ids))  # no duplicate ids


def test_active_formats_excludes_drafts():
    active = loader.active_formats()
    assert all(f["status"] == "active" for f in active)
    assert len(active) < len(loader.load_formats())  # drafts exist and are excluded


def test_min_relevance_filter():
    high = loader.active_formats(min_relevance=9)
    assert high and all((f["re_relevance"] or 0) >= 9 for f in high)


def test_get_format():
    assert loader.get_format("magazine_style_v1")["name"] == "Magazine Style"
    assert loader.get_format("does_not_exist") is None


def test_format_menu_contains_blueprints():
    menu = loader.format_menu(min_relevance=MIN_FORMAT_RELEVANCE)
    assert "### magazine_style_v1 — Magazine Style" in menu
    assert "blueprint:" in menu and "use_when:" in menu
    # low-relevance D2C promo formats stay out of the selector menu
    assert "bundle_deal_v1" not in menu


# ── strategy: protocol surface ───────────────────────────────────────────────

def test_implements_full_prompt_strategy_protocol():
    s = AtelierStrategy()
    ctx = _ctx()
    for method in ("build_copy_system_prompt", "build_copy_user_brief",
                   "build_image_prompt_system", "build_meta_copy_system",
                   "build_image_prompt_brief", "build_image_gen_system"):
        out = getattr(s, method)(ctx)
        assert isinstance(out, str) and out.strip(), method
    assert isinstance(s.variation_hints(), list) and len(s.variation_hints()) == 4
    assert isinstance(s.build_image_gen_prompt("base", None, 0), str)


# ── strategy: copy contract ──────────────────────────────────────────────────

def test_copy_system_keeps_adcopy_json_contract():
    out = AtelierStrategy().build_copy_system_prompt(_ctx())
    for key in ('"headline"', '"body_copy"', '"cta"', '"variations"', '"visual_hint"'):
        assert key in out
    assert "EXACTLY 4 variations" in out
    assert "Book Now" in out  # the verbatim CTA label list


def test_meta_copy_system_keeps_platform_contract():
    out = AtelierStrategy().build_meta_copy_system(_ctx())
    for key in ('"primary_text"', '"headline"', '"description"', '"call_to_action"'):
        assert key in out
    assert "BOOK_NOW" in out


def test_copy_brief_carries_project_and_meta_copy():
    ctx = _ctx(meta_ad_copy={"headline": ["H1", "H2"], "primary_text": ["P1"]})
    out = AtelierStrategy().build_copy_user_brief(ctx)
    assert "Godrej Brooklyn Avenue" in out
    assert "Karthik" in out and "Zero-commute" in out
    assert "APPROVED META AD COPY" in out and "H2" in out and "P1" in out


# ── strategy: selector ───────────────────────────────────────────────────────

def test_selector_system_embeds_menu_and_output_contract():
    out = AtelierStrategy().build_image_prompt_system(_ctx())
    assert "FORMAT LIBRARY" in out
    assert "magazine_style_v1" in out
    assert "[format: <chosen_format_id>]" in out


def test_image_prompt_brief_reflects_missing_images():
    out = AtelierStrategy().build_image_prompt_brief(_ctx(has_product_images=False))
    assert "No project images attached" in out


# ── strategy: final prompt assembly ──────────────────────────────────────────

def test_format_marker_split():
    fid, rest = AtelierStrategy.split_format_marker(
        "[format: magazine_style_v1]\n\nFull-bleed editorial photo…")
    assert fid == "magazine_style_v1"
    assert rest.startswith("Full-bleed editorial")
    fid2, rest2 = AtelierStrategy.split_format_marker("no marker here")
    assert fid2 is None and rest2 == "no marker here"


def test_image_gen_prompt_strips_marker_and_injects_copy_verbatim():
    s = AtelierStrategy()
    ad = _AdCopy([_Var("Skip the school run", "3.5 BHK | ₹2.1 Cr | KPHB", "dusk facade")],
                 cta="Book Now")
    out = s.build_image_gen_prompt("[format: key_features_v1]\n\nBlueprint body.", ad, 0)
    assert "[format:" not in out
    assert out.startswith("Blueprint body.")
    assert 'Headline: "Skip the school run"' in out
    assert 'Body copy: "3.5 BHK | ₹2.1 Cr | KPHB"' in out
    assert 'CTA: "Book Now"' in out
    assert "Variation direction: dusk facade" in out


def test_image_gen_prompt_cycles_variations_and_falls_back_to_hints():
    s = AtelierStrategy()
    ad = _AdCopy([_Var("A", "1", ""), _Var("B", "2", "")])
    out = s.build_image_gen_prompt("base", ad, 3)          # 3 % 2 -> variation B
    assert 'Headline: "B"' in out
    assert "Variation direction:" in out                    # empty hint -> stock hint
    out2 = s.build_image_gen_prompt("base", None, 1)        # no ad copy at all
    assert "Copy for this variation" not in out2
    assert s.variation_hints()[1].split(":")[0] in out2


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
