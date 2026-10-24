"""LLM provider selection: local Ollama or cloud Claude / OpenAI / Gemini.

A model is addressed by a spec string:

    "phi4:14b"                      -> Ollama (no prefix = local, backwards compatible)
    "ollama/phi4:14b"               -> Ollama
    "anthropic/claude-sonnet-5-5"   -> Anthropic Claude   (ANTHROPIC_API_KEY)
    "openai/gpt-4.1"                -> OpenAI             (OPENAI_API_KEY)
    "gemini/gemini-2.5-flash"       -> Google Gemini      (GOOGLE_API_KEY)

Cloud integrations are optional packages imported only when selected
(langchain-anthropic, langchain-openai, langchain-google-genai).
Cloud providers receive the metric summary and, if entered, the anamnesis.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    api_key_env: str | None
    package: str


PROVIDERS = {
    "ollama": Provider("ollama", "Local (Ollama)", None, "langchain-ollama"),
    "anthropic": Provider("anthropic", "Anthropic Claude", "ANTHROPIC_API_KEY", "langchain-anthropic"),
    "openai": Provider("openai", "OpenAI", "OPENAI_API_KEY", "langchain-openai"),
    "gemini": Provider("gemini", "Google Gemini", "GOOGLE_API_KEY", "langchain-google-genai"),
}

# Small local model used for query extraction and relevance filtering.
LOCAL_FAST_MODEL = "llama3.2"


def parse_model_spec(spec: str) -> tuple[str, str]:
    """Split "provider/model" into its parts; unprefixed names are Ollama models."""
    spec = (spec or "").strip()
    prefix, sep, model = spec.partition("/")
    if sep and prefix.lower() in PROVIDERS:
        return prefix.lower(), model
    return "ollama", spec


def is_local(spec: str) -> bool:
    return parse_model_spec(spec)[0] == "ollama"


def provider_of(spec: str) -> Provider:
    return PROVIDERS[parse_model_spec(spec)[0]]


def display_name(spec: str) -> str:
    provider, model = parse_model_spec(spec)
    return f"{model}  ·  {PROVIDERS[provider].label}"


def is_configured(spec: str) -> bool:
    """True for Ollama models and for cloud models whose API key is set."""
    env = provider_of(spec).api_key_env
    return env is None or bool(os.getenv(env))


def fast_model_for(spec: str) -> str:
    """Model for lightweight agents: the small local model when running locally,
    otherwise the selected cloud model (no silent fallback to another provider)."""
    return LOCAL_FAST_MODEL if is_local(spec) else spec


def installed_ollama_models() -> list[str] | None:
    """Models pulled into the local Ollama server, or None if it cannot be reached."""
    try:
        import ollama

        return sorted(m.model for m in ollama.list().models if m.model)
    except Exception:
        return None


def chat_model(spec: str, temperature: float = 0.2, json_mode: bool = False):
    """Return a LangChain chat model for the spec."""
    provider, model = parse_model_spec(spec)
    if not model:
        raise ValueError("No model name given.")
    if not is_configured(spec):
        raise RuntimeError(f"{PROVIDERS[provider].label} requires the {PROVIDERS[provider].api_key_env} environment variable.")
    try:
        if provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(model=model, temperature=temperature, **({"format": "json"} if json_mode else {}))
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            # No JSON mode: callers ask for JSON in the prompt and use extract_json.
            return ChatAnthropic(model=model, temperature=temperature, max_tokens=4096)
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            kwargs = {"model_kwargs": {"response_format": {"type": "json_object"}}} if json_mode else {}
            return ChatOpenAI(model=model, temperature=temperature, **kwargs)
        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            kwargs = {"response_mime_type": "application/json"} if json_mode else {}
            return ChatGoogleGenerativeAI(model=model, temperature=temperature, **kwargs)
    except ImportError as exc:
        raise RuntimeError(
            f"{PROVIDERS[provider].label} support needs `pip install {PROVIDERS[provider].package}`."
        ) from exc
    raise ValueError(f"Unknown provider: {provider}")


def response_text(response) -> str:
    """Normalise LangChain message content (str or list of content blocks) to text."""
    content = response.content
    if isinstance(content, list):
        content = "".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)
    return str(content).strip()


def extract_json(text: str) -> str:
    """Strip markdown fences / prose around a JSON value so json.loads can parse it."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        json.loads(text)
        return text
    except ValueError:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        return match.group(1) if match else text
