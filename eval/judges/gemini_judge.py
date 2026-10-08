"""Gemini 2.5 Flash judge via the official google-genai SDK."""
from __future__ import annotations
import os, time, json
from typing import Any, Dict
from google import genai
from google.genai import types
from .base import JudgeClient, JudgeResponse, call_with_retries


def _strip_unsupported(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Gemini's response_schema is a subset of JSON-Schema. Recursively drop
    keys it doesn't accept (`additionalProperties`, `$schema`, `strict`)."""
    if isinstance(schema, dict):
        out = {}
        for k, v in schema.items():
            if k in ("additionalProperties", "$schema", "strict"):
                continue
            out[k] = _strip_unsupported(v)
        return out
    if isinstance(schema, list):
        return [_strip_unsupported(x) for x in schema]
    return schema


class GeminiJudge(JudgeClient):
    name = "gemini-2.5-flash"
    provider = "gemini"

    def __init__(self, model: str = "gemini-2.5-flash", api_key: str | None = None):
        self.model = model
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=key)
        self.name = model

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Dict[str, Any],
    ) -> JudgeResponse:
        t0 = time.time()
        cleaned = _strip_unsupported(json_schema)
        try:
            resp = call_with_retries(lambda: self.client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=cleaned,
                ),
            ))
        except Exception as e:
            return JudgeResponse(
                parsed=None, raw_text="", latency_s=time.time() - t0,
                tokens_in=0, tokens_out=0, error=f"{type(e).__name__}: {e}",
            )

        latency = time.time() - t0
        raw = resp.text or ""
        usage = getattr(resp, "usage_metadata", None)
        tokens_in  = getattr(usage, "prompt_token_count", 0) if usage else 0
        tokens_out = getattr(usage, "candidates_token_count", 0) if usage else 0
        try:
            parsed = json.loads(raw)
            err = None
        except Exception as e:
            parsed, err = None, f"json_parse_error: {e}"
        return JudgeResponse(
            parsed=parsed, raw_text=raw, latency_s=latency,
            tokens_in=tokens_in, tokens_out=tokens_out, error=err,
        )
