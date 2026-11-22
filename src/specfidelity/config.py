"""Config loader: extends, file references, overrides, sweeps, interpolation, validation.

All paths are relative to the repo root (the directory containing pyproject.toml).
See docs/design.md for the model.
"""

from __future__ import annotations

import copy
import glob
import itertools
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REF_SUFFIXES = (".yaml", ".yml")
FILE_SUFFIXES = (".md", ".txt", ".v", ".sv", ".svh", ".vh")
REQUIRED_EXPERIMENT_KEYS = ("name", "suite", "agent", "model", "eval")
_INTERP = re.compile(r"\$\{([A-Za-z0-9_.]+)\}")


class ConfigError(Exception):
    pass


def find_repo_root(start: Path | None = None) -> Path:
    p = (start or Path.cwd()).resolve()
    for d in (p, *p.parents):
        if (d / "pyproject.toml").exists():
            return d
    raise ConfigError("could not find repo root (no pyproject.toml above cwd)")


# --------------------------------------------------------------------------- loading


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"referenced file does not exist: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def deep_merge(base: dict, over: dict) -> dict:
    """Dicts merge recursively; lists and scalars in `over` replace `base`."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_with_extends(rel: str, root: Path, _chain: tuple[str, ...] = ()) -> dict:
    if rel in _chain:
        raise ConfigError(f"extends cycle: {' -> '.join((*_chain, rel))}")
    data = _read_yaml(root / rel)
    parent = data.pop("extends", None)
    if parent:
        data = deep_merge(load_with_extends(parent, root, (*_chain, rel)), data)
    return data


# --------------------------------------------------------------------------- dotted keys


def get_dotted(d: dict, key: str) -> Any:
    cur: Any = d
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(key)
        cur = cur[part]
    return cur


def set_dotted(d: dict, key: str, value: Any) -> None:
    parts = key.split(".")
    cur = d
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
        if not isinstance(cur, dict):
            raise ConfigError(f"cannot set {key}: {part} is not a mapping")
    cur[parts[-1]] = value


def apply_overrides(cfg: dict, overrides: list[str]) -> dict:
    cfg = copy.deepcopy(cfg)
    for ov in overrides:
        if "=" not in ov:
            raise ConfigError(f"override must be key=value, got {ov!r}")
        k, v = ov.split("=", 1)
        set_dotted(cfg, k.strip(), yaml.safe_load(v))
    return cfg


# --------------------------------------------------------------------------- sweeps


def expand_sweep(cfg: dict) -> list[dict]:
    sweep = cfg.get("sweep")
    if not sweep:
        return [cfg]
    keys = list(sweep)
    variants = []
    for combo in itertools.product(*(sweep[k] for k in keys)):
        v = {k: val for k, val in cfg.items() if k != "sweep"}
        v = copy.deepcopy(v)
        tags = []
        for k, val in zip(keys, combo):
            set_dotted(v, k, val)
            tags.append(f"{k.split('.')[-1]}={Path(val).stem if isinstance(val, str) else val}")
        v["variant"] = ",".join(tags)
        variants.append(v)
    return variants


# --------------------------------------------------------------------------- refs + interpolation


def resolve_refs(node: Any, root: Path, _chain: tuple[str, ...] = ()) -> Any:
    if isinstance(node, dict):
        return {k: resolve_refs(v, root, _chain) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve_refs(v, root, _chain) for v in node]
    if isinstance(node, str) and node.endswith(REF_SUFFIXES):
        if node in _chain:
            raise ConfigError(f"reference cycle: {' -> '.join((*_chain, node))}")
        inner = resolve_refs(load_with_extends(node, root), root, (*_chain, node))
        inner["_source"] = node
        return inner
    return node


def interpolate(cfg: dict) -> dict:
    def sub(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: sub(v) for k, v in node.items()}
        if isinstance(node, list):
            return [sub(v) for v in node]
        if isinstance(node, str):
            def repl(m: re.Match) -> str:
                try:
                    return str(get_dotted(cfg, m.group(1)))
                except KeyError:
                    raise ConfigError(f"unknown interpolation ${{{m.group(1)}}}") from None
            return _INTERP.sub(repl, node)
        return node

    return sub(cfg)


# --------------------------------------------------------------------------- validation


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _walk_files(node: Any, path: str = ""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_files(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_files(v, f"{path}[{i}]")
    elif isinstance(node, str) and node.endswith(FILE_SUFFIXES) and "/" in node:
        yield path, node


def suite_designs(suite: dict, root: Path) -> list[Path]:
    dirs: set[Path] = set()
    for pattern in suite.get("include", []):
        for m in glob.glob(str(root / pattern)):
            if (Path(m) / "design.yaml").exists():
                dirs.add(Path(m))
    out = []
    for d in sorted(dirs):
        meta = _read_yaml(d / "design.yaml")
        if all(meta.get(k) == v for k, v in (suite.get("filters") or {}).items()):
            out.append(d)
    return out


def validate(cfg: dict, root: Path) -> Report:
    r = Report()
    for k in REQUIRED_EXPERIMENT_KEYS:
        if k not in cfg:
            r.errors.append(f"missing required key: {k}")
    for where, rel in _walk_files(cfg):
        if not (root / rel).exists():
            r.errors.append(f"{where}: file not found: {rel}")

    enabled = {fb.get("name") for fb in cfg.get("feedback", []) if isinstance(fb, dict)}
    for stage in (cfg.get("agent") or {}).get("stages", []):
        wanted = stage.get("feedback")
        if isinstance(wanted, list):
            for name in set(wanted) - enabled:
                r.warnings.append(
                    f"agent stage {stage.get('id')!r} wants feedback {name!r}, "
                    "which this experiment does not enable"
                )

    if isinstance(cfg.get("suite"), dict) and not suite_designs(cfg["suite"], root):
        r.errors.append("suite matches no designs")
    return r


# --------------------------------------------------------------------------- entry point


def load_experiment(rel: str, overrides: list[str] | None = None, root: Path | None = None):
    """Return a list of (resolved_config, Report), one per sweep variant."""
    root = root or find_repo_root()
    rel = str(Path(rel).resolve().relative_to(root)) if Path(rel).is_absolute() else rel
    base = apply_overrides(load_with_extends(rel, root), overrides or [])
    results = []
    for variant in expand_sweep(base):
        cfg = interpolate(resolve_refs(variant, root))
        cfg["_source"] = rel
        results.append((cfg, validate(cfg, root)))
    return results
