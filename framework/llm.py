"""2. LLM call logic: sends prompts to OpenRouter and returns an LLMCall record."""

from framework.models import LLMCall, ModelConfig


def call_llm(model: ModelConfig, prompt: str, seed: int | None = None) -> LLMCall:
    """Call OpenRouter and return the prompt, raw response, tokens, cost, and wall time."""
    raise NotImplementedError
