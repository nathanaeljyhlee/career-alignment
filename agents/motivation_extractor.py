"""
Agent 2: Motivation Extractor (Qwen 7B)

Parses the candidate's WHY statement into structured motivational themes
across 7 dimensions. Used downstream for role-motivation alignment scoring.
"""
import logging
from typing import Any

import ollama
from pydantic import BaseModel, Field

from config import get_tuning, extraction_model

logger = logging.getLogger(__name__)


class MotivationTheme(BaseModel):
    """A single motivational dimension with score and evidence."""
    dimension: str
    score: float = Field(description="0-1 intensity of this motivation", ge=0.0, le=1.0)
    evidence: str = Field(description="Quote or paraphrase from WHY statement supporting this score")
    label: str = Field(description="high, moderate, or low")


class MotivationProfile(BaseModel):
    """Full motivation extraction output."""
    themes: list[MotivationTheme] = Field(default_factory=list)
    primary_driver: str = Field(description="The single strongest motivational dimension")
    secondary_driver: str = Field(description="The second strongest dimension")
    why_quality: str = Field(description="rich, adequate, or thin — how much signal was in the WHY")
    summary: str = Field(description="1-2 sentence synthesis of what drives this candidate")


MOTIVATION_PROMPT = """You are a career motivation analyzer for MBA students. You receive a WHY statement (why the candidate wants certain roles/industries) and extract structured motivational themes.

DIMENSIONS TO SCORE (0.0 to 1.0):
1. impact_orientation: Desire to create measurable change in the world (0=indifferent, 1=mission-driven)
2. capital_allocation: Interest in resource/investment decisions (0=no interest, 1=core motivation)
3. innovation: Draw to new technologies, products, approaches (0=prefers proven, 1=seeks cutting-edge)
4. leadership_scale: Preference for team/org size (0=individual contributor, 1=large org leadership)
5. autonomy: Independent vs structured work preference (0=structured/corporate, 1=entrepreneurial/independent)
6. stability_vs_volatility: Startup vs established preference (0=stable/established, 1=volatile/high-growth)
7. prestige_sensitivity: Brand/reputation importance (0=brand-indifferent, 1=brand-driven)

SCORING GUIDE:
- high (>= 0.65): Strong signal in WHY statement. Multiple mentions or central theme.
- moderate (0.35-0.64): Some signal but not dominant. Mentioned but not emphasized.
- low (< 0.35): Absent or contradicted. Not mentioned or actively deprioritized.

WHY QUALITY:
- "rich": 3+ dimensions clearly expressed, specific examples, clear reasoning
- "adequate": 1-2 dimensions clear, others inferrable
- "thin": Vague, short, or generic. Limited signal for matching.

Return ONLY valid JSON:
{{
  "themes": [
    {{
      "dimension": "impact_orientation",
      "score": 0.0,
      "evidence": "string",
      "label": "high|moderate|low"
    }}
  ],
  "primary_driver": "string",
  "secondary_driver": "string",
  "why_quality": "rich|adequate|thin",
  "summary": "string"
}}

Include ALL 7 dimensions in the themes array, even if score is 0.

--- WHY STATEMENT ---
{why_text}
"""


def extract_motivation(why_text: str) -> MotivationProfile:
    """Run motivation extraction on a WHY statement.

    Args:
        why_text: The candidate's free-text WHY statement

    Returns:
        MotivationProfile with 7 scored dimensions
    """
    min_length = get_tuning("motivation_extraction", "min_why_length") or 200

    # Check WHY quality upfront
    if len(why_text.strip()) < min_length:
        logger.warning(
            "WHY statement is %d chars (minimum %d for reliable extraction). "
            "Results may be shallow.",
            len(why_text.strip()), min_length,
        )

    prompt = MOTIVATION_PROMPT.format(why_text=why_text)

    try:
        response = ollama.chat(
            model=extraction_model(),
            messages=[{"role": "user", "content": prompt}],
            format=MotivationProfile.model_json_schema(),
            options={
                "temperature": get_tuning("models", "extraction_temperature") or 0.1,
                "num_predict": 2048,
            },
        )
        content = response["message"]["content"]
        profile = MotivationProfile.model_validate_json(content)

        # Apply label thresholds
        for theme in profile.themes:
            if theme.score >= 0.65:
                theme.label = "high"
            elif theme.score >= 0.35:
                theme.label = "moderate"
            else:
                theme.label = "low"

        return profile

    except Exception as e:
        logger.error("Motivation extraction failed: %s", e)
        raise
