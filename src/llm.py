"""Minimal provider-agnostic LLM client. Pick the provider with env vars; no keys are stored in code.

  LLM_PROVIDER = gemini | anthropic | openai | fake   (if unset, chosen from whichever API key is set)
  GEMINI_API_KEY (or GOOGLE_API_KEY) / ANTHROPIC_API_KEY / OPENAI_API_KEY
  CLAIM_LLM_MODEL  optional model override
"""
from __future__ import annotations

import base64
import os
import time

DEFAULT_MODELS = {"anthropic": "claude-haiku-4-5", "openai": "gpt-4o-mini", "gemini": "gemini-3.8-flash"}


class AnthropicLLM:
    def __init__(self, model: str | None = None):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = model or os.getenv("CLAIM_LLM_MODEL") or DEFAULT_MODELS["anthropic"]

    def complete(self, system: str, user: str, max_tokens: int = 300, images: list[bytes] | None = None) -> str:
        content = user if not images else [
            *({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(i).decode()}} for i in images),
            {"type": "text", "text": user}]
        r = self.client.messages.create(model=self.model, max_tokens=max_tokens, temperature=0,
                                        system=system, messages=[{"role": "user", "content": content}])
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


class OpenAILLM:
    def __init__(self, model: str | None = None):
        from openai import OpenAI
        self.client = OpenAI()
        self.model = model or os.getenv("CLAIM_LLM_MODEL") or DEFAULT_MODELS["openai"]

    def complete(self, system: str, user: str, max_tokens: int = 300, images: list[bytes] | None = None) -> str:
        content = user if not images else [
            *({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(i).decode()}} for i in images),
            {"type": "text", "text": user}]
        r = self.client.chat.completions.create(model=self.model, max_tokens=max_tokens, temperature=0,
                                                messages=[{"role": "system", "content": system},
                                                          {"role": "user", "content": content}])
        return r.choices[0].message.content or ""


class GeminiLLM:
    """Google AI Studio (Gemini API). Retries with a wait on rate-limit errors, common on the free tier."""

    def __init__(self, model: str | None = None, client=None, retries: int = 4, wait_s: float = 15.0):
        if client is None:
            from google import genai
            key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not key:
                raise RuntimeError("set GEMINI_API_KEY (your Google AI Studio key)")
            client = genai.Client(api_key=key)
        self.client = client
        self.model = model or os.getenv("CLAIM_LLM_MODEL") or DEFAULT_MODELS["gemini"]
        self.retries, self.wait_s = retries, wait_s

    def complete(self, system: str, user: str, max_tokens: int = 300, images: list[bytes] | None = None) -> str:
        contents = user
        if images:
            from google.genai import types
            contents = [*(types.Part.from_bytes(data=i, mime_type="image/png") for i in images), user]
        cfg = {"system_instruction": system, "temperature": 0, "max_output_tokens": max(max_tokens * 4, 4096)}  # thinking models spend part of this budget before answering
        for attempt in range(self.retries + 1):
            try:
                r = self.client.models.generate_content(model=self.model, contents=contents, config=cfg)
                return r.text or ""
            except Exception as e:  # noqa: BLE001 - SDK raises several error types for rate limits
                msg = str(e)
                if "NOT_FOUND" in msg and "model" in msg.lower():
                    raise RuntimeError(
                        f"Gemini model '{self.model}' is not available for your key. Pick a current model in Google AI Studio "
                        f"and run: export CLAIM_LLM_MODEL=<model name>") from e
                transient = any(t in msg for t in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"))
                if not transient or attempt == self.retries:
                    raise
                time.sleep(self.wait_s * (attempt + 1))
        return ""


class FakeLLM:
    """Returns a canned reply. For tests."""
    def __init__(self, reply: str = "[]"):
        self.reply = reply

    def complete(self, system: str, user: str, max_tokens: int = 300, images: list[bytes] | None = None) -> str:
        return self.reply


def detect_provider(env=None) -> str:
    env = os.environ if env is None else env
    if env.get("LLM_PROVIDER"):
        return env["LLM_PROVIDER"].lower()
    if env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY"):
        return "gemini"
    if env.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if env.get("OPENAI_API_KEY"):
        return "openai"
    raise RuntimeError("no LLM configured: set GEMINI_API_KEY (or ANTHROPIC_API_KEY / OPENAI_API_KEY)")


def get_llm(provider: str | None = None):
    provider = (provider or detect_provider()).lower()
    if provider == "gemini":
        return GeminiLLM()
    if provider == "anthropic":
        return AnthropicLLM()
    if provider == "openai":
        return OpenAILLM()
    if provider == "fake":
        return FakeLLM()
    raise ValueError(f"unknown LLM provider: {provider}")