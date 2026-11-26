"""LLM provider layer: Grok by xAI (primary) and Ollama (optional local).

Both are called through the OpenAI-compatible Chat Completions API with the official `openai` Python client:
  xAI    -> https://api.x.ai/v1            (Bearer XAI_API_KEY)
  Ollama -> http://localhost:11434/v1      (no key)
Includes timeout handling, retry with exponential backoff for rate limits / transient errors (honouring
Retry-After), token-usage reporting, and error messages that never contain the API key.
"""
import logging
import random
import time

import httpx
from openai import (APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, BadRequestError,
                    NotFoundError, OpenAI, PermissionDeniedError, RateLimitError)

from .core import get_setting

log = logging.getLogger("agrimind.llm")
MAX_RETRIES = 3
BACKOFF_BASE = 1.5
MAX_WAIT = 20.0
_sleep = time.sleep  # patched in tests


class LLMUnavailable(Exception):
    """Raised when no answer can be produced. `kind` is one of: config, auth, rate_limit, timeout, network,
    model, bad_request, server."""

    def __init__(self, message: str, kind: str = "server"):
        super().__init__(message)
        self.kind = kind


def _provider():
    p = get_setting("llm_provider")
    return "xai" if p in ("xai", "grok", "gemini") else p  # 'gemini' from an older install migrates to xAI


def provider_info():
    p = _provider()
    if p == "xai":
        return {"provider": "xai", "label": "Grok (xAI)", "model": get_setting("xai_model"),
                "base_url": get_setting("xai_base_url"), "configured": bool(get_setting("xai_api_key"))}
    return {"provider": "ollama", "label": "Ollama (local)", "model": get_setting("ollama_model"),
            "base_url": get_setting("ollama_url"), "configured": True}


def _client(timeout: float):
    p = _provider()
    if p == "xai":
        key = get_setting("xai_api_key")
        if not key:
            raise LLMUnavailable("Grok is not configured: add an xAI API key in Admin → Model configuration "
                                 "or set XAI_API_KEY in backend/.env.", "config")
        base, model = get_setting("xai_base_url").rstrip("/"), get_setting("xai_model")
    elif p == "ollama":
        key, base, model = "ollama", get_setting("ollama_url").rstrip("/") + "/v1", get_setting("ollama_model")
    else:
        raise LLMUnavailable(f"Unknown LLM provider '{p}'.", "config")
    client = OpenAI(api_key=key, base_url=base, max_retries=0,
                    timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)))
    return client, p, model, key


def _clean(msg: str, key: str | None):
    msg = str(msg)
    if key and key != "ollama":
        msg = msg.replace(key, "***")
    return msg[:400]


def _retry_after(e) -> float | None:
    try:
        v = e.response.headers.get("retry-after")
        return min(MAX_WAIT, float(v)) if v else None
    except Exception:  # noqa: BLE001
        return None


def _usage(u):
    if not u:
        return None
    d = {"prompt_tokens": getattr(u, "prompt_tokens", None), "completion_tokens": getattr(u, "completion_tokens", None),
         "total_tokens": getattr(u, "total_tokens", None), "reasoning_tokens": None}
    det = getattr(u, "completion_tokens_details", None)
    if det is not None:
        d["reasoning_tokens"] = getattr(det, "reasoning_tokens", None)
    return d


def generate(system: str, messages: list[dict], temperature: float | None = None, timeout: float | None = None,
             max_tokens: int | None = None) -> dict:
    """messages: [{'role': 'user'|'assistant', 'content': str}].
    Returns {text, latency_ms, provider, model, usage, retries, finish_reason}."""
    t = float(get_setting("temperature")) if temperature is None else temperature
    timeout = float(timeout or get_setting("llm_timeout"))
    client, p, model, key = _client(timeout)
    label = "Grok (xAI)" if p == "xai" else "Ollama"
    kwargs = {"model": model, "temperature": t, "messages": [{"role": "system", "content": system}] + messages}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    t0 = time.perf_counter()
    attempt = 0
    while True:
        try:
            r = client.chat.completions.create(**kwargs)
            break
        except AuthenticationError as e:
            raise LLMUnavailable(f"{label} rejected the API key (401). Check the key in Admin → Model configuration.", "auth") from e
        except PermissionDeniedError as e:
            raise LLMUnavailable(f"{label} denied access (403): {_clean(e.message, key)}", "auth") from e
        except NotFoundError as e:
            raise LLMUnavailable(f"Model '{model}' was not found on {label} (404). Use 'List available models' in Admin to pick one.", "model") from e
        except BadRequestError as e:
            raise LLMUnavailable(f"{label} rejected the request (400): {_clean(e.message, key)}", "bad_request") from e
        except (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError) as e:
            status = getattr(e, "status_code", None)
            transient = isinstance(e, (RateLimitError, APITimeoutError, APIConnectionError)) or (status or 0) >= 500
            if not transient or attempt >= MAX_RETRIES:
                if isinstance(e, RateLimitError):
                    raise LLMUnavailable(f"{label} rate limit or quota reached (429) after {attempt + 1} attempts. "
                                         "Wait a minute, or check your xAI team's limits and credits in the xAI Console.", "rate_limit") from e
                if isinstance(e, APITimeoutError):
                    raise LLMUnavailable(f"{label} did not respond within {timeout:.0f} s ({attempt + 1} attempts). "
                                         "Try again or raise the timeout in Admin.", "timeout") from e
                if isinstance(e, APIConnectionError):
                    raise LLMUnavailable(f"Could not connect to {label} at {client.base_url} ({attempt + 1} attempts). "
                                         "Check the internet connection" + (" or that `ollama serve` is running." if p == "ollama" else "."), "network") from e
                raise LLMUnavailable(f"{label} error {status}: {_clean(getattr(e, 'message', e), key)}", "server") from e
            wait = _retry_after(e) or min(MAX_WAIT, BACKOFF_BASE * (2 ** attempt)) + random.uniform(0, 0.5)
            log.warning("%s transient error (%s); retry %d/%d in %.1fs", label, type(e).__name__, attempt + 1, MAX_RETRIES, wait)
            attempt += 1
            _sleep(wait)
    choice = r.choices[0] if r.choices else None
    text = (choice.message.content or "").strip() if choice else ""
    if not text:
        raise LLMUnavailable(f"{label} returned an empty answer (finish_reason={getattr(choice, 'finish_reason', None)}).", "server")
    return {"text": text, "latency_ms": round((time.perf_counter() - t0) * 1000, 1), "provider": p,
            "model": getattr(r, "model", None) or model, "usage": _usage(getattr(r, "usage", None)),
            "retries": attempt, "finish_reason": getattr(choice, "finish_reason", None)}


def list_models():
    p = _provider()
    try:
        client, _, _, key = _client(20)
        return {"provider": p, "models": sorted(m.id for m in client.models.list().data)}
    except LLMUnavailable as e:
        return {"provider": p, "models": [], "error": str(e)}
    except Exception as e:  # noqa: BLE001
        k = get_setting("xai_api_key") if p == "xai" else None
        return {"provider": p, "models": [], "error": _clean(f"{type(e).__name__}: {e}", k)}
