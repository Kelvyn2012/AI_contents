"""
AI Service: prompt templates per content type + provider call.
"""
import logging
from .providers import generate_text

logger = logging.getLogger(__name__)

SYSTEM_BASE = (
    "You are an expert marketing copywriter and content strategist. "
    "Write high-quality, engaging content that matches the brand voice and audience."
)

PROMPT_TEMPLATES = {
    "blog_post": (
        "Write a comprehensive, SEO-optimised blog post for the brand '{brand_name}'. "
        "Tone: {tone}. Target audience: {audience}. "
        "Keywords to naturally include: {keywords}. "
        "Additional instructions: {extra}. "
        "Include: catchy title, introduction, 3-5 H2 sections, and a conclusion with CTA. "
        "Minimum 600 words."
    ),
    "product_description": (
        "Write a compelling product description for '{brand_name}'. "
        "Tone: {tone}. Target audience: {audience}. "
        "Key features/keywords: {keywords}. "
        "Additional context: {extra}. "
        "Include: headline, 3 bullet benefits, full paragraph description, and CTA. "
        "Around 250 words."
    ),
    "ad_copy": (
        "Write 3 variations of high-converting ad copy for '{brand_name}'. "
        "Tone: {tone}. Target audience: {audience}. "
        "Keywords: {keywords}. "
        "Additional notes: {extra}. "
        "Each variation: headline (max 30 chars), primary text (max 125 chars), description (max 30 chars). "
        "Format clearly as Variation 1, 2, 3."
    ),
    "email_sequence": (
        "Write a 3-email nurture sequence for '{brand_name}'. "
        "Tone: {tone}. Target audience: {audience}. "
        "Key themes/keywords: {keywords}. "
        "Additional context: {extra}. "
        "Each email: subject line, preview text, and full body with clear CTA. "
        "Email 1: Welcome/Intro. Email 2: Value/Education. Email 3: Offer/Conversion."
    ),
}

MAX_TOKENS = {
    "blog_post": 2000,
    "product_description": 600,
    "ad_copy": 600,
    "email_sequence": 1800,
}


def generate_content(project, content_type: str, prompt_extra: str = "") -> str:
    """
    Build prompt from project context and generate content.
    Returns the raw text string.
    """
    template = PROMPT_TEMPLATES.get(content_type)
    if not template:
        raise ValueError(f"Unknown content type: {content_type}")

    user_prompt = template.format(
        brand_name=project.brand_name,
        tone=project.tone,
        audience=project.audience,
        keywords=", ".join(project.keyword_list()),
        extra=prompt_extra or "None",
    )

    max_tokens = MAX_TOKENS.get(content_type, 1500)
    logger.debug("Generating %s for project %s", content_type, project.id)
    return generate_text(SYSTEM_BASE, user_prompt, max_tokens=max_tokens)
