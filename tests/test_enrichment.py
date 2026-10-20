"""Unit tests for public email extraction and content theme classification."""

from src.enrichment.extractor import (
    extract_email_from_text,
    extract_themes_from_text,
)


def test_extract_valid_email_from_bio():
    """Verify extracting clean email from multi-line text."""
    bio = """
    Software engineer and AI creator.
    For sponsorships and business inquiries, reach out at collab@creatorlab.io.
    Subscribe for weekly tutorials!
    """
    email = extract_email_from_text(bio)
    assert email == "collab@creatorlab.io"


def test_extract_email_missing_or_empty():
    """Empty or None text must return 'Not Found'."""
    assert extract_email_from_text(None) == "Not Found"
    assert extract_email_from_text("") == "Not Found"
    assert extract_email_from_text("   ") == "Not Found"
    assert extract_email_from_text("No contact information shared here.") == "Not Found"


def test_reject_asset_extensions_and_placeholders():
    """Asset files like icon@2x.png and placeholder domains like @example.com must be rejected."""
    text_with_asset = "Download my app assets from asset@2x.png or visit my channel."
    assert extract_email_from_text(text_with_asset) == "Not Found"

    text_with_placeholder = "Contact me at user@example.com for dummy tests."
    assert extract_email_from_text(text_with_placeholder) == "Not Found"

    text_with_domain_com = "Reach out at hello@domain.com."
    assert extract_email_from_text(text_with_domain_com) == "Not Found"


def test_prioritize_business_line():
    """When multiple emails exist, prioritize line with 'business' or 'contact' keywords."""
    text = """
    Random email mentioned: newsletter@techupdates.org
    For business inquiries: partnership@alexrivera.com
    Another mention: random@somewhere.net
    """
    email = extract_email_from_text(text)
    assert email == "partnership@alexrivera.com"


def test_extract_themes_matching():
    """Verify theme keyword extraction against tech taxonomy."""
    text = "Building autonomous AI agents using LangChain, Python, and PyTorch for deep learning."
    themes = extract_themes_from_text(text)

    assert "Artificial Intelligence" in themes
    assert "Python Programming" in themes
    assert "Deep Learning" in themes
    assert "Large Language Models" in themes


def test_extract_themes_fallback():
    """When text has no tech keywords, fall back to default themes."""
    text = "Vlogging my daily life and morning routines."
    themes = extract_themes_from_text(text, default_themes=["Lifestyle"])
    assert themes == ["Lifestyle"]

