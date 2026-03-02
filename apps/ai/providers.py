"""
OpenAI-compatible provider abstraction.
Swap out OPENAI_API_BASE in .env to use any compatible endpoint.
"""
import logging
from openai import OpenAI
from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
        )
    return _client


def generate_text(system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> str:
    """
    Call the AI provider and return the text result.
    Raises RuntimeError on failure.
    """
    client = get_client()
    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("AI provider error: %s", exc)
        raise RuntimeError(f"AI generation failed: {exc}") from exc
