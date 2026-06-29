import os

import httpx


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 800


class LLMServiceError(RuntimeError):
    pass


def answer_with_context(question: str, contexts: list[dict]) -> dict:
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("LLM_MODEL", DEFAULT_MODEL)
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS))

    context_text = _format_contexts(contexts)

    if not api_key:
        return {
            "mode": "retrieval_only",
            "answer": (
                "LLM_API_KEY is not configured. The system has retrieved the most "
                "relevant paper chunks, but did not call a large language model."
            ),
            "model": None,
            "context": context_text,
        }

    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI paper reading assistant. Answer only from the provided "
                "paper context. If the context is insufficient, say that the paper "
                "context does not contain enough evidence."
            ),
        },
        {
            "role": "user",
            "content": f"Paper context:\n{context_text}\n\nQuestion:\n{question}",
        },
    ]

    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException as exc:
        raise LLMServiceError(
            "LLM request timed out. Check network, VPN/proxy, or use another "
            "OpenAI-compatible LLM_BASE_URL."
        ) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise LLMServiceError(
            f"LLM API returned HTTP {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.RequestError as exc:
        raise LLMServiceError(f"LLM request failed: {exc}") from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMServiceError("LLM API returned an unexpected response format.") from exc

    return {
        "mode": "llm",
        "answer": data["choices"][0]["message"]["content"],
        "model": model,
        "context": context_text,
    }


def _format_contexts(contexts: list[dict]) -> str:
    parts = []

    for index, item in enumerate(contexts, start=1):
        metadata = item.get("metadata", {})
        chunk_index = metadata.get("chunk_index", "unknown")
        text = item.get("text", "")
        parts.append(f"[Context {index} | chunk {chunk_index}]\n{text}")

    return "\n\n".join(parts)
