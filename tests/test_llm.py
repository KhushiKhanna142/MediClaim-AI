import pytest

import src.llm as llm
from src.llm import GeminiLLM, detect_provider


class Resp:
    def __init__(self, text):
        self.text = text


class StubClient:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return Resp(o)


def test_detect_provider_from_keys():
    assert detect_provider({"GEMINI_API_KEY": "x"}) == "gemini"
    assert detect_provider({"GOOGLE_API_KEY": "x"}) == "gemini"
    assert detect_provider({"ANTHROPIC_API_KEY": "x"}) == "anthropic"
    assert detect_provider({"LLM_PROVIDER": "OpenAI", "GEMINI_API_KEY": "x"}) == "openai"
    with pytest.raises(RuntimeError):
        detect_provider({})


def test_gemini_returns_text_and_sends_system_prompt():
    c = StubClient(['["a query"]'])
    out = GeminiLLM(client=c).complete("be brief", "question?")
    assert out == '["a query"]'
    model, contents, cfg = c.calls[0]
    assert contents == "question?" and cfg["system_instruction"] == "be brief" and cfg["temperature"] == 0


def test_gemini_retries_on_rate_limit(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    c = StubClient([Exception("429 RESOURCE_EXHAUSTED quota"), Exception("503 UNAVAILABLE"), "ok"])
    assert GeminiLLM(client=c).complete("s", "u") == "ok" and len(c.calls) == 3


def test_gemini_does_not_retry_other_errors(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    c = StubClient([Exception("400 invalid argument"), "ok"])
    with pytest.raises(Exception, match="400"):
        GeminiLLM(client=c).complete("s", "u")
    assert len(c.calls) == 1


def test_gemini_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    c = StubClient([Exception("429")] * 10)
    with pytest.raises(Exception, match="429"):
        GeminiLLM(client=c, retries=2).complete("s", "u")
    assert len(c.calls) == 3


def test_gemini_model_not_found_gives_actionable_error(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    c = StubClient([Exception("404 NOT_FOUND. This model models/old-flash is no longer available")])
    with pytest.raises(RuntimeError, match="CLAIM_LLM_MODEL"):
        GeminiLLM(client=c, model="old-flash").complete("s", "u")
    assert len(c.calls) == 1