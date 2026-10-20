"""Extracts public business emails and content themes from text."""

import re
from typing import List, Optional

from src.utils.logger import get_logger

logger = get_logger("enrichment.extractor")

# Regex to locate candidate email patterns
EMAIL_CANDIDATE_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# File extensions and asset patterns that can falsely resemble emails (e.g. icon@2x.png)
DISALLOWED_EXTENSIONS = {
    "png", "jpg", "jpeg", "webp", "gif", "svg", "bmp", "tiff",
    "mp4", "mp3", "mov", "avi", "js", "css", "html", "php", "zip",
}

# Generic placeholder domains that do not represent genuine business inboxes
PLACEHOLDER_DOMAINS = {
    "example.com", "domain.com", "email.com", "test.com", "sample.com",
    "placeholder.com", "yourdomain.com", "yoursite.com", "company.com",
}

# Business and sponsorship context keywords for prioritizing inquiries
BUSINESS_KEYWORDS = (
    "business",
    "contact",
    "partnership",
    "sponsorship",
    "inquiries",
    "inquiry",
    "collaboration",
    "collab",
    "booking",
)

# Tech & AI content theme dictionary mapping keywords to standardized theme tags
TECH_THEME_TAXONOMY = {
    "Machine Learning": [r"\bmachine learning\b", r"\bml\b", r"\bscikit-learn\b"],
    "Deep Learning": [r"\bdeep learning\b", r"\bneural networks?\b", r"\bpytorch\b", r"\btensorflow\b"],
    "Artificial Intelligence": [r"\bartificial intelligence\b", r"\bai\b", r"\bagents?\b", r"\bgenai\b"],
    "Large Language Models": [r"\bllms?\b", r"\blarge language models?\b", r"\bgpt\b", r"\btransformers?\b", r"\blangchain\b"],
    "Python Programming": [r"\bpython\b", r"\bpandas\b", r"\bnumpy\b"],
    "Data Science": [r"\bdata science\b", r"\bdata analyst\b", r"\bdata analysis\b", r"\bbig data\b"],
    "Computer Vision": [r"\bcomputer vision\b", r"\bopencv\b", r"\byolo\b"],
    "NLP": [r"\bnlp\b", r"\bnatural language processing\b"],
    "Cloud & MLOps": [r"\bmlops\b", r"\bdocker\b", r"\bkubernetes\b", r"\baws\b", r"\bgcp\b", r"\bazure\b"],
    "Robotics": [r"\brobotics\b", r"\bros\b", r"\brobot\b"],
    "Software Engineering": [r"\bsoftware engineering\b", r"\bdeveloper\b", r"\bcoding\b", r"\bprogramming\b"],
    "Tech Reviews & Hardware": [r"\bhardware\b", r"\bgpu\b", r"\bbenchmarks?\b", r"\btech review\b"],
}


def extract_email_from_text(text: Optional[str]) -> str:
    """
    Extract a single genuine contact email address from supplied public text.
    Prioritizes email addresses located on lines or in immediate preceding context
    containing business, partnership, sponsorship, or inquiry keywords.

    Returns:
        str: Validated lowercase email, or 'Not Found' if no valid email is present.
    """
    if not text or not isinstance(text, str):
        return "Not Found"

    clean_text = text.strip()
    if not clean_text:
        return "Not Found"

    matches = list(EMAIL_CANDIDATE_REGEX.finditer(clean_text))
    if not matches:
        return "Not Found"

    valid_matches = []
    for match in matches:
        candidate_lower = match.group(0).lower().strip()
        parts = candidate_lower.split("@")
        if len(parts) != 2:
            continue
        local_part, domain_part = parts

        if not local_part or not domain_part:
            continue

        ext = domain_part.split(".")[-1]
        if ext in DISALLOWED_EXTENSIONS:
            continue

        if domain_part in PLACEHOLDER_DOMAINS:
            continue

        if ".." in domain_part or ".." in local_part:
            continue

        valid_matches.append((match, candidate_lower))

    if not valid_matches:
        return "Not Found"

    # Strategy 1: Check the specific line containing each email for business keywords
    lines = clean_text.splitlines()
    for match, candidate_lower in valid_matches:
        for line in lines:
            line_lower = line.lower()
            if candidate_lower in line_lower:
                if any(keyword in line_lower for keyword in BUSINESS_KEYWORDS):
                    return candidate_lower

    # Strategy 2: Check immediate preceding context (up to 60 characters before the match)
    for match, candidate_lower in valid_matches:
        start = max(0, match.start() - 60)
        preceding = clean_text[start:match.start()].lower()
        if any(keyword in preceding for keyword in BUSINESS_KEYWORDS):
            return candidate_lower

    # Strategy 3: Fall back to the first valid candidate
    return valid_matches[0][1]


def extract_themes_from_text(
    text: Optional[str],
    default_themes: Optional[List[str]] = None,
) -> List[str]:
    """
    Scan description or bio text against technology / AI taxonomy to identify content themes.

    Returns:
        List[str]: Unique list of identified themes, or default_themes if none match.
    """
    if not text or not isinstance(text, str):
        return default_themes or ["Technology"]

    identified: List[str] = []
    text_lower = text.lower()

    for theme, patterns in TECH_THEME_TAXONOMY.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                identified.append(theme)
                break

    if not identified:
        return default_themes or ["Technology"]

    return identified
