"""GPT-5 Nano judge via the official OpenAI SDK."""
from __future__ import annotations
import os, time, json
from typing import Any, Dict
from openai import OpenAI
from .base import JudgeClient, JudgeResponse, call_with_retries


class OpenAIJudge(JudgeClient):
    name = "gpt-5-nano"
    provider = "openai"

    def __init__(self, model: str = "gpt-5-nano", api_key: str | None = None):
        self.model = model
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
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
