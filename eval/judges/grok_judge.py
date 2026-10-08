"""Grok 4.1 Fast via xAI's OpenAI-compatible endpoint."""
from __future__ import annotations
import os, time, json
from typing import Any, Dict
from openai import OpenAI
from .base import JudgeClient, JudgeResponse, call_with_retries


class GrokJudge(JudgeClient):
    name = "grok-4-1-fast"
    provider = "xai"

    def __init__(self, model: str = "grok-4-1-fast", api_key: str | None = None,
                 base_url: str = "https://api.x.ai/v1"):
        self.model = model
        self.client = OpenAI(
            api_key=api_key or os.environ.get("XAI_API_KEY"),
            base_url=base_url,
        )
        self.name = model

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Dict[str, Any],
    ) -> JudgeResponse:
        t0 = time.time()
        try:
            resp = call_with_retries(lambda: self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "scoring",
                        "strict": True,
                        "schema": json_schema,
                    },
                },
            ))
        except Exception as e:
            return JudgeResponse(
                parsed=None, raw_text="", latency_s=time.time() - t0,
                tokens_in=0, tokens_out=0, error=f"{type(e).__name__}: {e}",
            )

        latency = time.time() - t0
        raw = resp.choices[0].message.content or ""
        usage = resp.usage
        try:
            parsed = json.loads(raw)
            err = None
        except Exception as e:
            parsed, err = None, f"json_parse_error: {e}"
        return JudgeResponse(
            parsed=parsed, raw_text=raw, latency_s=latency,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            error=err,
            extra={"finish_reason": resp.choices[0].finish_reason},
        )
