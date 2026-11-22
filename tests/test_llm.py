"""Tests for framework/llm.py (token lookup, code block extraction, and live OpenRouter call)."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from framework.config import load_yaml
from framework.llm import call_llm, extract_code_block, get_api_key
from framework.models import ModelConfig


def test_token_lookup():
    with TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # 1. Plain-text token file
        txt_file = tmp_dir / "token.txt"
        txt_file.write_text("sk-or-test-plain\n")

        # 2. JSON token file (inside a directory)
        tokens_dir = tmp_dir / ".tokens"
        tokens_dir.mkdir()
        json_file = tokens_dir / "user.json"
        json_file.write_text(json.dumps({"openrouter": {"api_key": "sk-or-test-json"}}))

        old_env_key = os.environ.pop("OPENROUTER_API_KEY", None)
        old_env_file = os.environ.pop("OPENROUTER_TOKEN_FILE", None)
        try:
            assert get_api_key(str(txt_file)) == "sk-or-test-plain"
            assert get_api_key(str(json_file)) == "sk-or-test-json"
            assert get_api_key(str(tokens_dir)) == "sk-or-test-json"
            assert get_api_key(str(tmp_dir)) == "sk-or-test-json"

            # Env var takes priority over token_file
            os.environ["OPENROUTER_API_KEY"] = "sk-or-test-env"
            assert get_api_key(str(json_file)) == "sk-or-test-env"
        finally:
            if old_env_key is not None:
                os.environ["OPENROUTER_API_KEY"] = old_env_key
            else:
                os.environ.pop("OPENROUTER_API_KEY", None)
            if old_env_file is not None:
                os.environ["OPENROUTER_TOKEN_FILE"] = old_env_file
            else:
                os.environ.pop("OPENROUTER_TOKEN_FILE", None)

    print("[PASS] Token lookup (env var, JSON file, plain-text file)")


def test_extract_code_block():
    sample = "Here is the testbench:\n```systemverilog\nmodule tb;\nendmodule\n```\n"
    assert extract_code_block(sample) == "module tb;\nendmodule\n"
    print("[PASS] Markdown Verilog code block extraction")


def test_live_openrouter_call():
    model = ModelConfig(**load_yaml("configs/models/gpt4o.yaml"))
    model.max_tokens = 32
    result = call_llm(
        model,
        "Reply with a one-line Verilog comment `// OPENROUTER_OK` inside a ```verilog code block.",
        seed=0,
    )
    assert "OPENROUTER_OK" in result.response
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
    assert result.wall_time_s > 0
    print(
        f"[PASS] Live OpenRouter call ({result.model}): "
        f"prompt_tokens={result.prompt_tokens}, completion_tokens={result.completion_tokens}, "
        f"cost_usd=${result.cost_usd:.6f}, wall_time_s={result.wall_time_s}s"
    )


def main():
    test_token_lookup()
    test_extract_code_block()
    test_live_openrouter_call()
    print("\nALL LLM TESTS PASSED")


if __name__ == "__main__":
    main()
