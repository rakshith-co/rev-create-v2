import pytest
from datetime import datetime, timezone
from schemas import Association, CreativeOut, GenerationOut, BrandInfo
from services.creative_registry import (
    CreativeType, CreativeSubtype, CreativeSource, SizeSpecs
)

def _make_creative_out(**kwargs):
    defaults = dict(
        id="abc",
        source=CreativeSource.GENERATED,
        metadata={
            "type": CreativeType.IMAGE,
            "subtype": CreativeSubtype.FEED_SQUARE,
            "size_specs": SizeSpecs(width=1080, height=1080, aspect_ratio="1:1", label="Feed Square"),
        },
        client_id="revspot",
        status="done",
        s3_key="creatives/abc.png",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return CreativeOut(**defaults)


def test_brand_info_handles_nulls():
    # Test with all fields as None (except company_name)
    b = BrandInfo(
        company_name="Test Co",
        tagline=None,
        brand_voice=None,
        target_personas=None,
        industry=None
    )
    assert b.company_name == "Test Co"
    assert b.tagline is None
    assert b.brand_voice == "professional"  # Default
    assert b.target_personas == []         # Default
    assert b.industry == "general"          # Default


def test_brand_info_partial_nulls():
    b = BrandInfo(
        company_name="Test Co",
        brand_voice="luxury"
    )
    assert b.brand_voice == "luxury"
    assert b.industry == "general"


def test_association_model():
    a = Association(type="project", id="proj-1")
    assert a.type == "project"
    assert a.id == "proj-1"


def test_creative_out_has_associations_not_project_id():
    c = _make_creative_out(associations=[Association(type="campaign", id="camp-1")])
    assert c.associations[0].type == "campaign"
    assert not hasattr(c, "project_id")


def test_creative_out_associations_defaults_to_empty():
    c = _make_creative_out()
    assert c.associations == []


def test_generation_out():
    c = _make_creative_out()
    g = GenerationOut(
        headline="Test",
        body_copy="Body",
        generated_cta="Click",
        image_prompt="prompt",
        images=[c],
    )
    assert len(g.images) == 1
    assert g.headline == "Test"


