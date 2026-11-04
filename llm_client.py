"""PDF section 5.3 — Gemini first, then Groq, then OpenRouter."""

import json
import re

import requests

from settings import env

TIMEOUT = 90


def has_key() -> bool:
    return bool(env("GEMINI_API_KEY") or env("GROQ_API_KEY") or env("OPENROUTER_API_KEY"))


def parse_json(text: str) -> dict:
    # Models sometimes wrap JSON in a ```json fence. Keep the object only.
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.M).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("model did not return JSON")
    data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON was not an object")
    return data


def _post(url: str, headers: dict, payload: dict) -> dict:
    response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:240]}")
    return response.json()


def _gemini(prompt: str) -> str:
    key = env("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is empty")
    model = env("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    try:
        data = _post(url, {}, {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
        })
    except Exception as exc:
        raise RuntimeError(str(exc).replace(key, "[key]")) from None
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _openai(base: str, key: str, model: str, prompt: str, json_mode: bool) -> str:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if "openrouter.ai" in base:
        headers["HTTP-Referer"] = "http://localhost"
        headers["X-Title"] = "c2c-outreach"
    payload = {
        "model": model,
        "temperature": 0.4,
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        data = _post(base, headers, payload)
    except RuntimeError:
        if not json_mode:
            raise
        # Some free models reject response_format. Ask again in plain text.
        payload.pop("response_format")
        data = _post(base, headers, payload)
    text = data["choices"][0]["message"]["content"]
    if not str(text).strip():
        raise RuntimeError("empty model response")
    return text


def _groq(prompt: str) -> str:
    key = env("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is empty")
    return _openai(
        "https://api.groq.com/openai/v1/chat/completions",
        key,
        env("GROQ_MODEL", "llama-3.3-70b-versatile"),
        prompt,
        True,
    )


def _openrouter(prompt: str, json_mode: bool) -> str:
    key = env("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is empty")
    return _openai(
        "https://openrouter.ai/api/v1/chat/completions",
        key,
        env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
        prompt,
        json_mode,
    )


def complete_json(prompt: str) -> dict:
    errors = []
    calls = []
    if env("GEMINI_API_KEY"):
        calls.append(("gemini", _gemini))
    if env("GROQ_API_KEY"):
        calls.append(("groq", _groq))
    if env("OPENROUTER_API_KEY"):
        calls.append(("openrouter", lambda prompt: _openrouter(prompt, True)))
    if not calls:
        raise RuntimeError("Add GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY to .env")
    for name, call in calls:
        try:
            return parse_json(call(prompt))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError("No model returned JSON. " + " | ".join(errors))


def complete_text(prompt: str) -> str:
    # Follow-ups use OpenRouter only (PDF section 5.4).
    return _openrouter(prompt, False).strip()
