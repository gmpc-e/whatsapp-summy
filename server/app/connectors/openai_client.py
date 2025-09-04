from __future__ import annotations
import os
import logging
from typing import List, Dict, Any
from openai import OpenAI

log = logging.getLogger("openai_client")

# Create a single client instance. Reads API key from env: OPENAI_API_KEY
_client: OpenAI | None = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=api_key)
    return _client

def chat_json(model: str, messages: List[Dict[str, str]], *, max_tokens: int = 1500, temperature: float = 0.2) -> str:
    """
    Calls the OpenAI Chat Completions API and requests a JSON object response.
    Returns the `message.content` string (which should be JSON).
    """
    client = _get_client()
    log.debug("OpenAI call: model=%s max_tokens=%d temperature=%.2f", model, max_tokens, temperature)
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
    )
    content = resp.choices[0].message.content or "{}"
    return content
