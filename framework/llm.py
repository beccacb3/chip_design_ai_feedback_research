"""LLM call logic: resolves the OpenRouter API key and sends chat completion requests.

API key lookup order:
  1. `OPENROUTER_API_KEY` environment variable.
  2. `OPENROUTER_TOKEN_FILE` environment variable, or `model.token_file`
     (can be a JSON file, a plain-text file, or a directory like `~/.tokens`
     or `~` to search for any JSON file containing `openrouter.api_key`).
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from framework.models import LLMCall, ModelConfig

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

CODE_BLOCK_RE = re.compile(
    r"```(?:systemverilog|verilog|sv|v)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def _read_key_from_file(path: Path) -> str | None:
    """Extract an OpenRouter key from a JSON or plain-text file, if present."""
    try:
        text = path.read_text().strip()
    except OSError:
        return None
    if not text:
        return None
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        key = (
            data.get("openrouter", {}).get("api_key")
            if isinstance(data.get("openrouter"), dict)
            else data.get("api_key")
        )
        return str(key).strip() if key else None
    return text


def get_api_key(token_file: str | None = "~/.tokens") -> str:
    """Resolve the OpenRouter API key from env var, file, or directory search."""
    env_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key

    target = os.environ.get("OPENROUTER_TOKEN_FILE") or token_file or "~"
    path = Path(target).expanduser()

    if path.is_file():
        key = _read_key_from_file(path)
        if key:
            return key

    search_dirs = []
    if path.is_dir():
        search_dirs.append(path)
        if (path / ".tokens").is_dir():
            search_dirs.insert(0, path / ".tokens")

    for directory in search_dirs:
        for candidate in sorted(directory.glob("*.json")):
            key = _read_key_from_file(candidate)
            if key:
                return key

    raise RuntimeError(
        "OpenRouter API key not found. Set OPENROUTER_API_KEY or place a token JSON in ~/.tokens/."
    )


def extract_code_block(response: str) -> str:
    """Extract Verilog/SystemVerilog code from markdown fences if present."""
    matches = CODE_BLOCK_RE.findall(response)
    if matches:
        return matches[-1].strip() + "\n"
    return response.strip() + "\n"


def call_llm(
    model: ModelConfig,
    prompt: str | list[dict[str, str]],
    seed: int | None = None,
) -> LLMCall:
    """Send a prompt (or message list) to OpenRouter and return an LLMCall record."""
    api_key = get_api_key(model.token_file)

    if isinstance(prompt, str):
        messages = [{"role": "user", "content": prompt}]
        prompt_record = prompt
    else:
        messages = prompt
        prompt_record = "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages)

    payload: dict = {
        "model": model.model_id,
        "messages": messages,
        "temperature": model.temperature,
        "max_tokens": model.max_tokens,
    }
    if seed is not None:
        payload["seed"] = seed

    request = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {err_body}") from exc
    wall_time_s = round(time.monotonic() - start, 4)

    content = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})

    return LLMCall(
        model=model.model_id,
        prompt=prompt_record,
        response=content,
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
        cost_usd=float(usage.get("cost", 0.0) or 0.0),
        wall_time_s=wall_time_s,
    )
