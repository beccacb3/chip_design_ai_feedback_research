# chip_design_ai_feedback_research

A config-driven framework for evaluating how faithfully agent-generated hardware
testbenches follow their specifications. Accompanies the CSCE689 State-of-the-Art
Critique Report.

See [`docs/design.md`](docs/design.md) for the repo layout and data contracts
([`framework/models.py`](framework/models.py)).

## Quick start

```bash
pip install -r requirements.txt

# Check all designs under designs/ and validate the experiment config
make check

# Print the resolved ExperimentConfig (after `extends:` and file references)
make show-config CONFIG=configs/experiments/no_self_check.yaml

# Preview importing VerilogEval files into designs/verilogeval/<name>/golden/...
python3 designs/standardize.py import-verilogeval raw/verilogeval verilogeval

# Build the Docker environment (Python + iverilog + verilator)
make image
```
