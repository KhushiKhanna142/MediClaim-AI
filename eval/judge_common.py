"""Judge LLM shared by the RAGAS and DeepEval runners.

Both libraries want a judge that returns structured (Pydantic) output. Instead of wiring each to a provider SDK, one core
asks the project's own LLM client (src.llm.get_llm, which already retries on rate limits) for JSON matching the requested
schema, validates it, and caches every answer on disk keyed by (model, prompt, schema). Reruns and interrupted runs are free,
and the same prompt always gets the same score.

Needs only the stdlib + pydantic here; ragas / deepeval are imported lazily by the adapter you actually use.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Optional, Type

from pydantic import BaseModel, ValidationError

SYSTEM = "You are a precise, impartial evaluation judge. Reply with a single JSON object and nothing else: no prose, no code fences."
SUFFIX = "\n\nRespond with ONLY one JSON object that conforms to this JSON schema:\n{schema}"


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in judge reply")
    return m.group(0)


class JudgeCore:
    def __init__(self, llm, cache_path: str | Path = "eval/results/judge_cache.json", pause: float = 0.0, max_tokens: int = 1500):
        self.llm, self.pause, self.max_tokens = llm, pause, max_tokens
        self.model_name = getattr(llm, "model", type(llm).__name__)
        self.cache_path = Path(cache_path)
        self.cache: dict[str, str] = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}
        self.calls = self.cache_hits = 0

    def _key(self, prompt: str, schema: Optional[dict]) -> str:
        return hashlib.sha256(json.dumps([self.model_name, prompt, schema], sort_keys=True).encode()).hexdigest()

    def _store(self, key: str, value: str) -> None:
        self.cache[key] = value
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache))
        tmp.replace(self.cache_path)

    def _ask(self, prompt: str) -> str:
        self.calls += 1
        reply = self.llm.complete(SYSTEM, prompt, max_tokens=self.max_tokens)
        if self.pause:
            time.sleep(self.pause)
        return reply

    def structured(self, prompt: str, model_cls: Type[BaseModel]) -> BaseModel:
        schema = model_cls.model_json_schema()
        key = self._key(prompt, schema)
        if key in self.cache:
            self.cache_hits += 1
            return model_cls.model_validate_json(self.cache[key])
        full = prompt + SUFFIX.format(schema=json.dumps(schema))
        try:
            obj = model_cls.model_validate_json(_extract_json(self._ask(full)))
        except (ValueError, ValidationError) as first:
            obj = model_cls.model_validate_json(_extract_json(self._ask(f"{full}\n\nYour previous reply was invalid ({str(first)[:300]}). Return corrected JSON only.")))
        self._store(key, obj.model_dump_json())
        return obj

    def text(self, prompt: str) -> str:
        key = self._key(prompt, None)
        if key in self.cache:
            self.cache_hits += 1
            return self.cache[key]
        out = self._ask(prompt)
        self._store(key, out)
        return out


# ------------------------------------------------------------------------------------------------ adapters
def ragas_judge(core: JudgeCore):
    """A ragas.llms InstructorBaseRagasLLM backed by `core` (ragas >= 0.4, `ragas.metrics.collections`)."""
    import asyncio

    from ragas.llms.base import InstructorBaseRagasLLM

    class RagasJudge(InstructorBaseRagasLLM):
        def generate(self, prompt, response_model):
            return core.structured(prompt, response_model)

        async def agenerate(self, prompt, response_model):
            return await asyncio.to_thread(core.structured, prompt, response_model)

    return RagasJudge()


def deepeval_judge(core: JudgeCore):
    """A DeepEvalBaseLLM backed by `core`."""
    from deepeval.models import DeepEvalBaseLLM

    class DeepEvalJudge(DeepEvalBaseLLM):
        def __init__(self):
            super().__init__(str(core.model_name))

        def load_model(self):
            return core

        def generate(self, prompt: str, schema: Optional[Type[BaseModel]] = None):
            return core.structured(prompt, schema) if schema else core.text(prompt)

        async def a_generate(self, prompt: str, schema: Optional[Type[BaseModel]] = None):
            return self.generate(prompt, schema)

        def get_model_name(self) -> str:
            return str(core.model_name)

    return DeepEvalJudge()