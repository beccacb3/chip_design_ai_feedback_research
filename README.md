# chip_design_ai_feedback_research

A config-driven framework for evaluating how faithfully agent-generated hardware
testbenches follow their specifications.

## Project documents
- **Master Primary Document (Phase 2_3 Research Ideation Report):**
  [Google Doc](https://docs.google.com/document/d/1e-iE2tZ_PjXUmcsaox_FkN8hZUYj909ze8gNukg219E/edit?tab=t.0#heading=h.zbjs7zyhjnha)
- **Phase 2_2 State-of-the-Art Critique Report:**
  [Google Doc](https://docs.google.com/document/d/1cQSQqJEJlWYoiBCev0xtpvcPGk5M4IZyx0uO-MyA7vk/edit?tab=t.6xadbu25koxn#heading=h.qom2o355zw38)
- **Framework Design & Contracts:**
  [`docs/design.md`](docs/design.md) and [`framework/models.py`](framework/models.py)

## Quick start

```bash
pip install -r requirements.txt

# Check all designs under designs/ and validate the experiment config
make check

# Print the resolved ExperimentConfig (after `extends:` and file references)
make show-config CONFIG=configs/experiments/e4_functional_coverage.yaml

# Run the infrastructure test suite (simulation, testing/feedback, and OpenRouter LLM)
make test

# Build the Docker environment (Python + iverilog + verilator)
make image
```
