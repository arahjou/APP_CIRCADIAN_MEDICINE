import pytest

from tools.llm_providers import chat_model, extract_json, fast_model_for, is_configured, parse_model_spec


@pytest.mark.parametrize("spec,expected", [
    ("phi4:14b", ("ollama", "phi4:14b")),
    ("ollama/qwen3:8b", ("ollama", "qwen3:8b")),
    ("anthropic/claude-sonnet-5-5", ("anthropic", "claude-sonnet-5-5")),
    ("openai/gpt-4.1", ("openai", "gpt-4.1")),
    ("gemini/gemini-2.5-flash", ("gemini", "gemini-2.5-flash")),
    ("hf.co/org/model:q4", ("ollama", "hf.co/org/model:q4")),
])
def test_parse_model_spec(spec, expected):
    assert parse_model_spec(spec) == expected


def test_fast_model_stays_with_selected_provider():
    assert fast_model_for("phi4:14b") == "llama3.2"
    assert fast_model_for("anthropic/claude-sonnet-5-5") == "anthropic/claude-sonnet-5-5"


def test_cloud_model_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not is_configured("openai/gpt-4.1")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        chat_model("openai/gpt-4.1")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert is_configured("openai/gpt-4.1")


@pytest.mark.parametrize("text", ['{"a": 1}', '```json\n{"a": 1}\n```', 'Here you go:\n{"a": 1}\nThanks'])
def test_extract_json(text):
    assert extract_json(text) == '{"a": 1}'
