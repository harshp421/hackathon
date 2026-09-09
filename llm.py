"""
Thin LLM wrapper. One place to swap providers.

Supports two backends, auto-detected from env:
  * Azure OpenAI  - set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY
                    (+ AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_VERSION)
  * OpenAI        - set OPENAI_API_KEY (+ OPENAI_MODEL)

If neither is configured, callers fall back to their offline path.
"""

import os

from dotenv import load_dotenv

load_dotenv()

def _get_llm_config(key: str, default: str = "") -> str:
    """Read from st.secrets if available, else os.environ."""
    try:
        import streamlit as st
        # check [azure][key]
        if "azure" in st.secrets and key.lower() in st.secrets["azure"]:
            return str(st.secrets["azure"][key.lower()]).strip()
        # check [llm][key]
        if "llm" in st.secrets and key.lower() in st.secrets["llm"]:
            return str(st.secrets["llm"][key.lower()]).strip()
        # check direct key in st.secrets
        if key in st.secrets:
            return str(st.secrets[key]).strip()
        if key.upper() in st.secrets:
            return str(st.secrets[key.upper()]).strip()
        if key.lower() in st.secrets:
            return str(st.secrets[key.lower()]).strip()
    except Exception:
        pass
    return (os.environ.get(key.upper()) or os.environ.get(key) or default).strip()


def get_azure_endpoint() -> str:
    return _get_llm_config("AZURE_OPENAI_ENDPOINT")


def get_azure_key() -> str:
    return _get_llm_config("AZURE_OPENAI_API_KEY")


def get_azure_deployment() -> str:
    return _get_llm_config("AZURE_OPENAI_DEPLOYMENT", default="gpt-4o")


def get_azure_api_version() -> str:
    return _get_llm_config("AZURE_OPENAI_API_VERSION", default="2025-01-01-preview")


def get_openai_key() -> str:
    return _get_llm_config("OPENAI_API_KEY") or _get_llm_config("api_key")


def get_openai_model() -> str:
    return _get_llm_config("OPENAI_MODEL", default="gpt-4o")


def _use_azure():
    return bool(get_azure_endpoint() and get_azure_key())


def _openai_key_ok():
    oa_key = get_openai_key()
    return len(oa_key) > 20 and not oa_key.startswith("sk-...")


def available():
    return _use_azure() or _openai_key_ok()


class _ModelProxy:
    def __str__(self):
        return get_azure_deployment() if _use_azure() else get_openai_model()
    def __repr__(self):
        return self.__str__()


MODEL = _ModelProxy()


def _azure_base_url():
    """Normalise whatever endpoint form was given down to '.../openai/v1/'."""
    raw = get_azure_endpoint()
    i = raw.find("/openai/v1")
    if i != -1:
        return raw[:i] + "/openai/v1/"
    return raw.rstrip("/") + "/openai/v1/"



_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    from openai import OpenAI

    if _use_azure():
        # The Azure "/openai/v1/" surface rejects the api-version query param;
        # only the older /openai/deployments/... path uses it.
        _client = OpenAI(base_url=_azure_base_url(), api_key=get_azure_key(), timeout=12.0)
    else:
        _client = OpenAI(api_key=get_openai_key() or None, timeout=12.0)
    return _client



def chat_json(system, user, max_tokens=300):
    """Return the model's reply as a raw JSON string (JSON mode forced)."""
    resp = _get_client().chat.completions.create(
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
    resp = _get_client().chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content


if __name__ == "__main__":
    print("backend:", "Azure OpenAI" if _use_azure() else "OpenAI")
    print("model  :", MODEL)
    if _use_azure():
        print("base   :", _azure_base_url())
        print("api-ver:", _AZ_API_VERSION)
    print("available:", available())
    if available():
        print("ping   :", chat_json('Reply with JSON.', 'Return {"ok": true} exactly.', max_tokens=20))
