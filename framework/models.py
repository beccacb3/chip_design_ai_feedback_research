"""Data models (contracts) shared across the framework.

Every YAML/JSON file on disk and every boundary between modules corresponds to
one of these dataclasses. Use `dataclasses.asdict(obj)` to serialize to dict.
"""

from dataclasses import dataclass, field


# --------------------------------------------------------------------- configs


@dataclass
class ModelConfig:
    """configs/models/*.yaml -- OpenRouter model settings."""
    name: str
    model_id: str                  # e.g. "openai/gpt-4o-2024-08-06"
    temperature: float = 0.2
    max_tokens: int = 8192


@dataclass
class FeedbackConfig:
    """configs/feedback/*.yaml -- one in-loop check the agent can run."""
    name: str                      # "compile", "simulate", "self_check", "coverage", "spec_check"
    tool: str                      # "iverilog", "verilator", "llm"
    args: list[str] = field(default_factory=list)
    options: dict = field(default_factory=dict)


@dataclass
class ExperimentConfig:
    """configs/experiments/*.yaml (after resolving `extends:` and file paths)."""
    name: str
    designs: str                   # path to designs/<group>
    model: ModelConfig
    prompts: dict[str, str]        # {"generate": "prompts/...", "find_root_cause": ..., "fix": ...}
    feedback: list[FeedbackConfig]
    max_iterations: int
    seeds: list[int]


# --------------------------------------------------------------------- designs


@dataclass
class Design:
    """designs/<group>/<name>/ -- ground-truth input and answer key."""
    name: str
    top_module: str
    original_name: str
    spec_path: str                 # designs/<group>/<name>/spec.md (given to agent)
    golden_rtl: list[str]          # designs/<group>/<name>/golden/rtl/*
    golden_tb: list[str] = field(default_factory=list)       # golden/tb/*
    golden_mutants: list[str] = field(default_factory=list)  # golden/mutants/*


# --------------------------------------------------------------------- run outputs


@dataclass
class Provenance:
    """Saved as runs/<exp>/<ts>_<sha>/provenance.json."""
    timestamp: str
    git_commit: str
    git_dirty: bool
    docker_image: str
    iverilog_version: str


@dataclass
class LLMCall:
    """One call to OpenRouter."""
    model: str
    prompt: str
    response: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    wall_time_s: float


@dataclass
class CheckResult:
    """Result of running one feedback check during the agent loop."""
    name: str
    passed: bool
    summary: str                   # fed back to the LLM if passed is False
    details: dict = field(default_factory=dict)


@dataclass
class Iteration:
    """One pass of generate (index 0) or fix (index 1..k)."""
    index: int
    testbench_path: str            # e.g. "generated_tb/iter_0.sv"
    llm_calls: list[LLMCall]
    checks: list[CheckResult]
    passed: bool


@dataclass
class DesignRun:
    """Saved as runs/.../<design>__seed<n>/run.json."""
    design: str
    seed: int
    iterations: list[Iteration]
    final_testbench: str           # "generated_tb/final.sv"
    final_passed: bool
    total_tokens: int
    total_cost_usd: float
    total_wall_time_s: float


@dataclass
class EvalResult:
    """Saved as runs/.../<design>__seed<n>/eval.json (scored against golden/)."""
    design: str
    seed: int
    compiles: bool                 # Eval0: compiles with golden/rtl/
    golden_rtl_passed: bool        # Eval1: accepts known-good golden/rtl/ (False = false positive)
    mutants_total: int
    mutants_killed: int
    mutation_score: float          # mutants_killed / mutants_total (Eval2)
    killed_list: list[str] = field(default_factory=list)
    survived_list: list[str] = field(default_factory=list)
