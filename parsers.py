"""
PDF parsing for resume and LinkedIn exports.

Uses pdfplumber for text extraction with section detection.
Output: structured dict with text organized by detected sections.
"""
from pathlib import Path
from typing import Any

import pdfplumber


# Common resume section headers (case-insensitive matching)
RESUME_SECTION_HEADERS = [
    "summary", "objective", "professional summary", "profile",
    "experience", "work experience", "professional experience", "employment",
    "education", "academic background",
    "skills", "technical skills", "core competencies", "competencies",
    "certifications", "licenses", "certificates",
    "projects", "key projects", "selected projects",
    "awards", "honors", "achievements",
    "publications", "research",
    "volunteer", "community", "leadership",
    "languages", "interests", "activities",
]

# LinkedIn PDF export section patterns
LINKEDIN_SECTION_HEADERS = [
    "experience", "education", "skills", "certifications",
    "honors & awards", "projects", "publications", "courses",
    "volunteer experience", "organizations", "languages",
    "recommendations", "summary", "about",
]


def _is_section_header(line: str, known_headers: list[str]) -> str | None:
    """Check if a line matches a known section header.
    Returns the normalized header name or None.
    """
    stripped = line.strip().rstrip(":").lower()
    # Remove common decorators (bullets, dashes, etc.)
    stripped = stripped.lstrip("-*|#> ").strip()

    for header in known_headers:
        if stripped == header or stripped.startswith(header + " "):
            return header
    return None


def _extract_text_from_pdf(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Extract text from PDF, page by page, with layout preservation."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text(layout=True) or ""
            pages.append({
                "page_number": i + 1,
                "text": text,
                "width": page.width,
                "height": page.height,
            })
    return pages


def _segment_into_sections(
    full_text: str, known_headers: list[str]
) -> dict[str, str]:
    """Split full text into sections based on detected headers.
    Returns dict mapping section_name -> section_text.
    Unmatched text goes into 'header' (top) or 'other'.
    """
    sections: dict[str, list[str]] = {"header": []}
    current_section = "header"

    for line in full_text.split("\n"):
        detected = _is_section_header(line, known_headers)
        if detected:
            current_section = detected
            if current_section not in sections:
                sections[current_section] = []
        else:
            sections.setdefault(current_section, []).append(line)

    return {k: "\n".join(v).strip() for k, v in sections.items() if v}


def parse_resume(pdf_path: str | Path) -> dict[str, Any]:
    """Parse a resume PDF into structured sections.

    Returns:
        {
            "raw_text": str,           # full concatenated text
            "pages": [...],            # per-page data
            "sections": {              # detected sections
                "header": "...",
                "experience": "...",
                "education": "...",
                ...
            },
            "source": "resume",
            "file_name": str,
        }
    """
    pdf_path = Path(pdf_path)
    pages = _extract_text_from_pdf(pdf_path)
    raw_text = "\n\n".join(p["text"] for p in pages)
    sections = _segment_into_sections(raw_text, RESUME_SECTION_HEADERS)

    return {
        "raw_text": raw_text,
        "pages": pages,
        "sections": sections,
        "source": "resume",
        "file_name": pdf_path.name,
    }


def parse_linkedin(pdf_path: str | Path) -> dict[str, Any]:
    """Parse a LinkedIn PDF export into structured sections.

    Returns same structure as parse_resume but with LinkedIn-specific
    section detection.
    """
    pdf_path = Path(pdf_path)
    pages = _extract_text_from_pdf(pdf_path)
    raw_text = "\n\n".join(p["text"] for p in pages)
    sections = _segment_into_sections(raw_text, LINKEDIN_SECTION_HEADERS)

    return {
        "raw_text": raw_text,
        "pages": pages,
        "sections": sections,
        "source": "linkedin",
        "file_name": pdf_path.name,
    }


def parse_pdf(pdf_path: str | Path, source_type: str = "resume") -> dict[str, Any]:
    """Unified parser entry point. source_type: 'resume' or 'linkedin'."""
    if source_type == "linkedin":
        return parse_linkedin(pdf_path)
    return parse_resume(pdf_path)
