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
    """Dicts merge recursively; lists and scalars in `over` replace `base`;
    a `null` value in `over` deletes the key (e.g. to disable a feedback mechanism)."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and _is_ref(out.get(k)) and "extends" not in v:
            # base says `prompt: x.yaml`, override says `prompt: {vars: ...}`:
            # tweak x.yaml rather than discarding it
            out[k] = {"extends": out[k], **copy.deepcopy(v)}
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
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
        base = load_with_extends(parent, root, (*_chain, rel))
        base.pop("abstract", None)  # abstract-ness is not inherited
        data = deep_merge(base, data)
    return data


# --------------------------------------------------------------------------- dotted keys


def get_dotted(d: dict, key: str) -> Any:
    cur: Any = d
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(key)
        cur = cur[part]
    return cur


def _is_ref(v: Any) -> bool:
    return isinstance(v, str) and v.endswith(REF_SUFFIXES)


def set_dotted(d: dict, key: str, value: Any) -> None:
    """Set a dotted key. If the path passes through a not-yet-loaded reference
    (`agent: configs/agents/x.yaml`), it is promoted to `{extends: ...}` so the
    override applies on top of the referenced config."""
    parts = key.split(".")
    cur = d
    for part in parts[:-1]:
        if _is_ref(cur.get(part)):
            cur[part] = {"extends": cur[part]}
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
    """Inline references. Two forms, usable anywhere in a config:

        prompt: configs/prompts/tb_from_spec.yaml          # reuse as-is
        prompt:                                            # reuse + tweak
          extends: configs/prompts/tb_from_spec.yaml
          vars: { checker: python }
    """
    if isinstance(node, list):
        return [resolve_refs(v, root, _chain) for v in node]
    if _is_ref(node):
        node = {"extends": node}
    if not isinstance(node, dict):
        return node
    if "extends" not in node:
        return {k: resolve_refs(v, root, _chain) for k, v in node.items()}

    parent = node["extends"]
    if parent in _chain:
        raise ConfigError(f"reference cycle: {' -> '.join((*_chain, parent))}")
    local = {k: v for k, v in node.items() if k != "extends"}
    base = load_with_extends(parent, root)
    base.pop("abstract", None)
    merged = deep_merge(base, local)
    out = {k: resolve_refs(v, root, (*_chain, parent)) for k, v in merged.items()}
    out["_source"] = parent if not local else f"{parent} (+ local overrides)"
    return out


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


KIND_REQUIRED = {
    "prompt": ("name", "template"),
    "agent": ("name", "control_loop", "stages"),
    "model": ("name", "provider", "model_id"),
    "feedback": ("name", "template"),
    "eval": ("name", "metrics"),
    "suite": ("name", "include"),
}
_PLACEHOLDER = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)(?:[:!][^}]*)?\}(?!\})")


def _check_component(node: Any, kind: str, where: str, root: Path, r: Report) -> None:
    if not isinstance(node, dict):
        r.errors.append(f"{where}: expected a {kind} config, got {node!r}")
        return
    if node.get("kind") != kind:
        r.errors.append(f"{where}: expected kind {kind!r}, got {node.get('kind')!r} "
                        f"(from {node.get('_source', 'inline')})")
        return
    for k in KIND_REQUIRED[kind]:
        if k not in node:
            r.errors.append(f"{where}: {kind} is missing required key {k!r}")
    if kind == "prompt" and (root / str(node.get("template", ""))).is_file():
        used = set(_PLACEHOLDER.findall((root / node["template"]).read_text()))
        known = set(node.get("required_vars") or []) | set(node.get("vars") or {})
        for name in sorted(used - known):
            r.errors.append(f"{where}: template uses {{{name}}} but it is neither in "
                            "vars nor required_vars")
        for name in sorted(set(node.get("required_vars") or []) - used):
            r.warnings.append(f"{where}: required var {name!r} is never used by the template")
    if kind == "feedback":
        _check_component(node.get("template"), "prompt", f"{where}.template", root, r)
    if kind == "agent":
        stages = node.get("stages")
        if not isinstance(stages, dict):
            r.errors.append(f"{where}.stages: must be a mapping keyed by stage id")
            return
        for sid, st in stages.items():
            if "prompt" in st:
                _check_component(st["prompt"], "prompt", f"{where}.stages.{sid}.prompt", root, r)
            for i, p in enumerate(st.get("prompts") or []):
                _check_component(p, "prompt", f"{where}.stages.{sid}.prompts[{i}]", root, r)


def validate(cfg: dict, root: Path) -> Report:
    r = Report()
    for k in REQUIRED_EXPERIMENT_KEYS:
        if k not in cfg:
            r.errors.append(f"missing required key: {k}")
    for where, rel in _walk_files(cfg):
        if not (root / rel).exists():
            r.errors.append(f"{where}: file not found: {rel}")

    for slot in ("suite", "agent", "model", "eval"):
        if slot in cfg:
            _check_component(cfg[slot], slot, slot, root, r)

    feedback = cfg.get("feedback") or {}
    if not isinstance(feedback, dict):
        r.errors.append("feedback: must be a mapping of name -> feedback config")
        feedback = {}
    for name, fb in feedback.items():
        _check_component(fb, "feedback", f"feedback.{name}", root, r)

    stages = (cfg.get("agent") or {}).get("stages")
    for sid, st in (stages.items() if isinstance(stages, dict) else []):
        wanted = st.get("feedback")
        if isinstance(wanted, list):
            for name in sorted(set(wanted) - set(feedback)):
                r.warnings.append(f"agent stage {sid!r} wants feedback {name!r}, "
                                  "which this experiment does not enable")

    if isinstance(cfg.get("suite"), dict) and not suite_designs(cfg["suite"], root):
        r.errors.append("suite matches no designs")
    return r


# --------------------------------------------------------------------------- entry point


def load_component(rel: str, root: Path | None = None) -> tuple[dict, Report]:
    """Resolve and validate a single component config (prompt, agent, feedback, ...)
    on its own. Configs marked `abstract: true` only need a valid `kind`."""
    root = root or find_repo_root()
    cfg = resolve_refs(rel, root)
    r = Report()
    kind = cfg.get("kind")
    if kind not in KIND_REQUIRED:
        r.errors.append(f"unknown or missing kind {kind!r} (expected one of {sorted(KIND_REQUIRED)})")
    elif not _read_yaml(root / rel).get("abstract"):
        _check_component(cfg, kind, kind, root, r)
    for where, f in _walk_files(cfg):
        if not (root / f).exists():
            r.errors.append(f"{where}: file not found: {f}")
    return cfg, r


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
