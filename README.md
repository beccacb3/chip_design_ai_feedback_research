# chip_design_ai_feedback_research

A small framework for running and comparing experiments on agent-generated
hardware testbenches. It accompanies the CSCE689 State-of-the-Art Critique Report.

See [`docs/design.md`](docs/design.md) for how it is organized.

## Usage

```bash
pip install -r requirements.txt

# Show an experiment's final config (after `extends:`) and any problems
python scripts/show_config.py configs/experiments/no_self_check.yaml

# Check that every design follows the standard layout
python scripts/standardize.py check

# Copy VerilogEval files into the standard layout (add --apply to write)
python scripts/standardize.py import-verilogeval raw/verilogeval verilogeval
```

The runner is not built yet.
