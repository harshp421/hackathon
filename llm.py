"""
Thin LLM wrapper. One place to swap providers.
Currently: OpenAI GPT-4o (Chat Completions). Reads OPENAI_API_KEY / OPENAI_MODEL from env.
"""

import os

from dotenv import load_dotenv

load_dotenv()

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")


def available():
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    # treat the .env.example placeholder as "not set" so the demo stays quiet
    return len(key) > 20 and not key.startswith("sk-...")


def _client():
    from openai import OpenAI

    return OpenAI()  # picks up OPENAI_API_KEY (and OPENAI_BASE_URL if set)


def chat_json(system, user, max_tokens=300):
    """Return the model's reply as a raw JSON string (JSON mode forced)."""
    resp = _client().chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content


def chat_text(system, user, max_tokens=1200):
    resp = _client().chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content
