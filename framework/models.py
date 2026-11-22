"""Data models (contracts) shared across framework/ and evaluation/.

Every YAML/JSON file on disk and every boundary between modules corresponds to
one of these dataclasses. Use `dataclasses.asdict(obj)` to serialize to dict.
"""

from dataclasses import dataclass, field


# --------------------------------------------------------------------- configs


@dataclass
class ModelConfig:
    """configs/models/*.yaml -> framework/llm.py."""
    name: str
    model_id: str                  # OpenRouter id, e.g. "openai/gpt-4o-2024-08-06"
    temperature: float = 0.2
    max_tokens: int = 8192


@dataclass
class DesignsConfig:
    """configs/designs/*.yaml -> designs/standardize.py."""
    name: str
    paths: list[str]               # design folders or globs (e.g. "designs/examples/counter4")


@dataclass
class SimulationConfig:
    """configs/simulation/*.yaml -> evaluation/simulation.py."""
    name: str
    tool: str                      # "iverilog", "verilator"
    args: list[str] = field(default_factory=list)
    timeout_s: int = 10


@dataclass
class TestingConfig:
    """configs/testing/*.yaml -> framework/testing.py -> evaluation/testbench.py."""
    name: str                      # "compile", "simulate", "self_check", "coverage", "spec_check"
    options: dict = field(default_factory=dict)


@dataclass
class FeedbackConfig:
    """configs/feedback/*.yaml -> framework/feedback.py."""
    name: str
    generate_prompt: str           # "prompts/generate_testbench.md"
    fix_prompt: str                # "prompts/fix_testbench.md"
    root_cause_prompt: str | None = None
    history: str = "full"          # "full" or "last_only"
    max_error_lines: int = 100


@dataclass
class FinalEvalConfig:
    """configs/final_eval/*.yaml -> evaluation/final.py & evaluation/report.py."""
    name: str
    metrics: list[str]


@dataclass
class ExperimentConfig:
    """configs/experiments/*.yaml (after resolving `extends:` and all 6 sections)."""
    name: str
    max_iterations: int
    seeds: list[int]
    model: ModelConfig
    designs: DesignsConfig
    simulation: SimulationConfig
    testing: list[TestingConfig]
    feedback: FeedbackConfig
    final_eval: FinalEvalConfig


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
    """Result of running one in-loop check from `testing`."""
    name: str
    passed: bool
    summary: str                   # self-contained text joined by feedback.py when passed is False
    details: dict = field(default_factory=dict)


@dataclass
class Iteration:
    """One pass of generate (index 0) or fix (index 1..k), saved in iterations/iter_<k>/."""
    index: int
    testbench_path: str            # e.g. "iterations/iter_0/testbench.sv"
    llm_calls: list[LLMCall]
    checks: list[CheckResult]
    passed: bool


@dataclass
class DesignRun:
    """Saved as runs/.../<design>__seed<n>/run.json."""
    design: str
    seed: int
    iterations: list[Iteration]
    final_testbench: str           # "final/testbench.sv"
    final_passed: bool
    total_tokens: int
    total_cost_usd: float
    total_wall_time_s: float


@dataclass
class EvalResult:
    """Saved as runs/.../<design>__seed<n>/final/eval.json (scored against golden/)."""
    design: str
    seed: int
    compiles: bool                 # Eval0: compiles with golden/rtl/
    golden_rtl_passed: bool        # Eval1: accepts known-good golden/rtl/ (False = false positive)
    mutants_total: int
    mutants_killed: int
    mutation_score: float          # mutants_killed / mutants_total (Eval2)
    killed_list: list[str] = field(default_factory=list)
    survived_list: list[str] = field(default_factory=list)
