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
    temperature: float = 0.0
    max_tokens: int = 8192
    token_file: str | None = "~/.tokens"


@dataclass
class DesignsConfig:
    """configs/designs/*.yaml -> designs/standardize.py."""
    name: str
    paths: list[str]               # design folders (e.g. "designs/fixme/mux")


@dataclass
class SimulationConfig:
    """configs/simulation/*.yaml -> evaluation/simulation.py."""
    name: str
    tool: str                      # "iverilog"
    args: list[str] = field(default_factory=list)
    timeout_s: int = 10


@dataclass
class TestingConfig:
    """configs/testing/*.yaml -> framework/testing.py -> evaluation/testbench.py."""
    name: str                      # "compile", "simulate", "requirement_groups", "req_code_coverage", "req_functional_coverage", "mutations"
    options: dict = field(default_factory=dict)


@dataclass
class FeedbackConfig:
    """configs/feedback/*.yaml -> framework/feedback.py."""
    name: str
    generate_prompt: str           # "prompts/generate_testbench.md"
    fix_prompt: str                # "prompts/fix_testbench.md"
    root_cause_prompt: str | None = None
    decompose_requirements: bool = False  # False in E1 (monolithic), True in E2-E4 (localized by requirement group)
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
class RequirementGroup:
    """One decomposed specification requirement group in design.yaml (used in E2-E4 & §4.1.6-4.1.7)."""
    id: str                        # e.g. "REQ_RESET"
    description: str               # human-readable requirement statement
    rtl_lines: list[int] = field(default_factory=list)            # 1-indexed lines in golden/rtl/ for E3 code coverage
    coverpoints: dict[str, str] = field(default_factory=dict)     # name -> Verilog boolean expr for E4 functional coverage


@dataclass
class Design:
    """designs/<group>/<name>/ -- ground-truth input and answer key."""
    name: str
    top_module: str
    original_name: str
    spec_path: str                 # designs/<group>/<name>/spec.md
    golden_rtl: list[str]          # designs/<group>/<name>/golden/rtl/*
    golden_tb: list[str] = field(default_factory=list)       # golden/tb/*
    golden_mutants: list[str] = field(default_factory=list)  # golden/mutants/*
    requirements: list[RequirementGroup] = field(default_factory=list)


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
    """Result of running one testbench check or final evaluation."""
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
    sim_wall_time_s: float = 0.0


@dataclass
class DesignRun:
    """Saved as runs/.../<design>__seed<n>/run.json."""
    design: str
    seed: int
    iterations: list[Iteration]
    final_testbench: str           # "final/testbench.sv"
    final_passed: bool
    total_tokens: int
    num_llm_calls: int
    total_cost_usd: float
    llm_wall_time_s: float
    sim_wall_time_s: float


@dataclass
class EvalResult:
    """Saved as runs/.../<design>__seed<n>/final/eval.json (Section 4.1.1 - 4.1.7 scorecard)."""
    design: str
    seed: int
    # 4.1.3 Golden RTL Acceptance
    compiles: bool
    golden_rtl_passed: bool
    false_positive: bool
    # 4.1.2 Mutation Testing
    mutants_total: int
    mutants_killed: int
    mutation_score: float
    # 4.1.5 Code Coverage
    code_coverage_score: float
    # 4.1.6 Requirement Group Coverage
    req_group_coverage_score: float
    # 4.1.7 Functional Coverage
    functional_coverage_score: float
    # 4.1.1 FixMe Golden Testbench Comparison
    golden_tb_functional_coverage: float
    missed_scenarios_vs_golden: list[str] = field(default_factory=list)
    extra_scenarios_over_golden: list[str] = field(default_factory=list)
    # 4.1.4 Computational Cost
    turns: int = 0
    num_llm_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    llm_wall_time_s: float = 0.0
    sim_wall_time_s: float = 0.0
    killed_list: list[str] = field(default_factory=list)
    survived_list: list[str] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
