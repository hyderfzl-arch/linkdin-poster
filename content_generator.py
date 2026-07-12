import logging

from openai import OpenAI

import config
from security import decrypt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a LinkedIn content strategist.
Write an engaging, professional LinkedIn post for {company_name}.
Company context: {company_context}
Language: {language}

Use the style and format of the example posts provided, but do not copy them.
Return only the post text (no labels, no markdown code fences)."""


def _get_client(api_key: str | None = None) -> OpenAI:
    key = api_key or config.OPENAI_API_KEY
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to your .env file or profile settings.")
    # max_retries and timeout make draft generation resilient to transient OpenAI errors.
    return OpenAI(api_key=key, max_retries=3, timeout=30)


def generate_post(
    example_posts: list[str],
    company_name: str = "",
    company_context: str = "",
    model: str = "gpt-4o",
    language: str = "en",
    api_key: str | None = None,
) -> str:
    if config.DEMO_MODE and not api_key:
        name = company_name or config.COMPANY_NAME or "Your Company"
        return (
            f"🚀 Big week at {name}.\n\n"
            "We’ve been talking to customers about the hardest part of staying visible on LinkedIn — "
            "and the answer is almost always the same: consistency beats perfection.\n\n"
            "So we built a workflow that turns your best posts into a steady stream of drafts, "
            "ready for your review and one-click publish.\n\n"
            "No blank pages. No late-night copywriting. Just your voice, scaled.\n\n"
            f"#{name.replace(' ', '')} #LinkedIn #ContentAutomation #AI #SmallBusiness"
        )

    client = _get_client(api_key)

    name = company_name or config.COMPANY_NAME
    ctx = company_context or config.COMPANY_CONTEXT

    if example_posts:
        joined_examples = "\n\n---\n\n".join(example_posts)
        user_content = (
            f"Here are some example LinkedIn posts to use as inspiration:\n\n{joined_examples}\n\n"
            f"Now write a new post for {name}."
        )
    else:
        user_content = f"Write a new LinkedIn post for {name}."

    system_msg = SYSTEM_PROMPT.format(
        company_name=name, company_context=ctx, language=language
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "developer", "content": system_msg},
                {"role": "user", "content": user_content},
            ],
            temperature=0.8,
            max_tokens=800,
        )
    except Exception as e:
        logger.exception("OpenAI draft generation failed")
        raise RuntimeError(f"OpenAI draft generation failed: {e}") from e

    content = resp.choices[0].message.content.strip()
    logger.info("Generated draft using model %s", model)
    return content
