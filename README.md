# chip_design_ai_feedback_research

A config-driven framework for evaluating how faithfully agent-generated hardware
testbenches follow their specifications. It accompanies the CSCE689 State-of-the-Art
Critique Report.

See [`docs/design.md`](docs/design.md) for the proposed design.

## Quick start

```bash
pip install -e .                      # or: export PYTHONPATH=src

# Inspect what an experiment resolves to (what a run would snapshot)
python -m specfidelity resolve configs/experiments/correctbench_gpt4o.yaml
python -m specfidelity plan    configs/experiments/sweep_models_iterations.yaml

# Content hygiene
python scripts/standardize.py check
python scripts/standardize.py import raw/verilog-eval/dataset_spec-to-rtl \
    --importer configs/importers/verilogeval.yaml --suite verilogeval_human   # dry run
python scripts/standardize.py index --apply
```

The runner (agent loop + feedback implementations) is not implemented yet.
