"""Comparison report: aggregates summary.json across runs/ into a table.

Entry point for `make report`:
    python3 -m evaluation.report runs/
"""

from pathlib import Path


def build_report(runs_root: Path) -> str:
    """Read summary.json from every run folder and return a comparison table."""
    raise NotImplementedError
