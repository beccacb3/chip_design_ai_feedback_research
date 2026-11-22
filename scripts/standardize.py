#!/usr/bin/env python3
"""Standardize benchmark content into the canonical designs/ layout.

  standardize.py import <raw_dir> --importer configs/importers/<x>.yaml --suite <name> [--apply] [--force]
  standardize.py check  [--no-configs]
  standardize.py index  [--apply]

Import and index are dry runs unless --apply is given. Raw files are copied, never moved.
See docs/design.md.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from specfidelity.config import ConfigError, load_experiment  # noqa: E402

DESIGNS = ROOT / "designs"
CIRCUIT_TYPES = {"combinational", "sequential"}
_MODULE = re.compile(r"^\s*module\s+([A-Za-z_][A-Za-z0-9_$]*)", re.MULTILINE)
_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)


# --------------------------------------------------------------------------- helpers


def normalize_id(name: str) -> str:
    """'Vector2-Rev', 'vector2 rev' -> 'vector2_rev'."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name.strip())
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return re.sub(r"_+", "_", s)


def modules_in(paths: list[Path]) -> list[str]:
    mods = []
    for p in paths:
        if p.exists():
            mods += _MODULE.findall(_COMMENTS.sub("", p.read_text(errors="replace")))
    return mods


def guess_circuit_type(paths: list[Path]) -> str:
    text = "".join(p.read_text(errors="replace") for p in paths if p.exists())
    return "sequential" if re.search(r"\b(posedge|negedge)\b", text) else "combinational"


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def as_list(v) -> list:
    return [] if v is None else v if isinstance(v, list) else [v]


# --------------------------------------------------------------------------- import


def cmd_import(args) -> int:
    imp = yaml.safe_load((ROOT / args.importer).read_text())
    pattern = re.compile(imp["id_pattern"])
    roles = imp["roles"]
    suite = normalize_id(args.suite)
    raw = Path(args.raw_dir).resolve()

    groups: dict[str, dict] = defaultdict(lambda: {"files": defaultdict(list), "originals": set()})
    unmatched = []
    for f in sorted(p for p in raw.rglob("*") if p.is_file()):
        m = pattern.match(f.name)
        if not m or m.group("role") not in roles:
            unmatched.append(f)
            continue
        did = normalize_id(m.group("id"))
        groups[did]["files"][m.group("role")].append(f)
        groups[did]["originals"].add(f.name[: m.start("role")].rstrip("_-."))

    existing = {p.parent.name: p.parent.parent.name for p in DESIGNS.glob("*/*/design.yaml")}
    problems = 0
    for did, g in sorted(groups.items()):
        dest = DESIGNS / suite / did
        copies, meta_files = [], defaultdict(list)
        for role, files in g["files"].items():
            spec = roles[role]
            for i, src in enumerate(files):
                target = spec["dest"].format(id=did)
                if len(files) > 1:  # several files for one role: keep them distinct
                    t = Path(target)
                    target = str(t.with_name(f"{t.stem}_{i}{t.suffix}"))
                copies.append((src, dest / target))
                meta_files[spec["field"]].append(target)

        notes = []
        if "spec" not in meta_files:
            notes.append("ERROR no spec file")
        if "rtl" not in meta_files:
            notes.append("ERROR no rtl file")
        if did in existing and existing[did] != suite:
            notes.append(f"WARN id also exists in suite {existing[did]!r}")
        if dest.exists() and not args.force:
            notes.append("SKIP destination exists (use --force)")
        if len(meta_files.get("spec", [])) > 1:
            notes.append("ERROR multiple spec files")

        rtl_src = [s for s, d in copies if rel(d).startswith(rel(dest / "rtl"))]
        mods = modules_in(rtl_src)
        aliases = imp.get("module_aliases", {})
        top = mods[0] if mods else did
        if imp.get("top_module_from_rtl") and mods and top in aliases:
            notes.append(f"WARN rtl module {top!r} aliased to {aliases[top]!r}")
        meta = {
            "id": did,
            "suite": suite,
            "top_module": top,
            "circuit_type": guess_circuit_type(rtl_src),
            "spec": (meta_files.get("spec") or ["spec.md"])[0],
            "rtl": meta_files.get("rtl", []),
            "golden_tb": meta_files.get("golden_tb", []),
            "mutants": meta_files.get("mutants", []),
            "source": {"dataset": imp["name"], "original_name": sorted(g["originals"])[0]},
            "aliases": sorted(g["originals"] - {did}),
        }
        if top in aliases:
            meta["module_aliases"] = {top: aliases[top]}

        problems += any(n.startswith("ERROR") for n in notes)
        status = "; ".join(notes) or "ok"
        print(f"{suite}/{did:<32} {len(copies)} files  [{status}]")
        if args.apply and not any(n.startswith(("ERROR", "SKIP")) for n in notes):
            for src, dst in copies:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            (dest / "design.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))

    if unmatched:
        print(f"\n{len(unmatched)} unmatched file(s):")
        for f in unmatched[:20]:
            print(f"  {rel(f)}")
        if len(unmatched) > 20:
            print("  ...")
    if not args.apply:
        print("\n(dry run; pass --apply to write)")
    return 1 if problems else 0


# --------------------------------------------------------------------------- check


def check_design(dy: Path) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    d = dy.parent
    try:
        meta = yaml.safe_load(dy.read_text()) or {}
    except yaml.YAMLError as e:
        return [f"invalid YAML: {e}"], []

    if meta.get("id") != d.name:
        errs.append(f"id {meta.get('id')!r} != directory name {d.name!r}")
    if normalize_id(d.name) != d.name:
        errs.append(f"directory name not canonical (expected {normalize_id(d.name)!r})")
    if meta.get("suite") != d.parent.name:
        errs.append(f"suite {meta.get('suite')!r} != parent directory {d.parent.name!r}")
    if meta.get("circuit_type") not in CIRCUIT_TYPES:
        errs.append(f"circuit_type must be one of {sorted(CIRCUIT_TYPES)}")

    spec = d / str(meta.get("spec", ""))
    if not meta.get("spec") or not spec.is_file():
        errs.append(f"spec not found: {meta.get('spec')}")
    elif not spec.read_text().strip():
        errs.append("spec is empty")

    for key in ("rtl", "golden_tb", "mutants"):
        for f in as_list(meta.get(key)):
            if not (d / f).is_file():
                errs.append(f"{key} not found: {f}")
    rtl = [d / f for f in as_list(meta.get("rtl"))]
    if not rtl:
        errs.append("no rtl listed")

    mods = modules_in(rtl)
    top = meta.get("top_module")
    aliases = meta.get("module_aliases") or {}
    if mods and top not in mods:
        hint = f" (alias of {list(aliases)})" if top in aliases.values() else ""
        (warns if hint else errs).append(f"top_module {top!r} not in rtl modules {mods}{hint}")
    if mods and len(set(mods)) != len(mods):
        warns.append(f"duplicate module names in rtl: {mods}")
    return errs, warns


def cmd_check(args) -> int:
    n_err = n_warn = 0
    seen: dict[str, list[str]] = defaultdict(list)
    alias_of: dict[str, str] = {}

    for dy in sorted(DESIGNS.glob("*/*/design.yaml")):
        errs, warns = check_design(dy)
        meta = yaml.safe_load(dy.read_text()) or {}
        key = f"{dy.parent.parent.name}/{dy.parent.name}"
        seen[dy.parent.name].append(key)
        for a in as_list(meta.get("aliases")):
            alias_of[normalize_id(a)] = key
        for e in errs:
            print(f"error   {key}: {e}")
        for w in warns:
            print(f"warning {key}: {w}")
        n_err += len(errs)
        n_warn += len(warns)

    for did, where in seen.items():
        if len(where) > 1:
            print(f"warning id {did!r} appears in multiple suites: {where}")
            n_warn += 1
    for alias, key in alias_of.items():
        if alias in seen and key not in seen[alias]:
            print(f"warning alias {alias!r} of {key} collides with design id in {seen[alias]}")
            n_warn += 1

    if not args.no_configs:
        for exp in sorted((ROOT / "configs/experiments").glob("*.y*ml")):
            try:
                for cfg, rep in load_experiment(rel(exp), root=ROOT):
                    tag = f"{rel(exp)}" + (f" [{cfg['variant']}]" if cfg.get("variant") else "")
                    for e in rep.errors:
                        print(f"error   {tag}: {e}")
                    for w in rep.warnings:
                        print(f"warning {tag}: {w}")
                    n_err += len(rep.errors)
                    n_warn += len(rep.warnings)
            except ConfigError as e:
                print(f"error   {rel(exp)}: {e}")
                n_err += 1

    n_designs = sum(len(v) for v in seen.values())
    print(f"\n{n_designs} design(s), {n_err} error(s), {n_warn} warning(s)")
    return 1 if n_err else 0


# --------------------------------------------------------------------------- index


def cmd_index(args) -> int:
    entries = []
    for dy in sorted(DESIGNS.glob("*/*/design.yaml")):
        m = yaml.safe_load(dy.read_text()) or {}
        entries.append({
            "id": m.get("id"),
            "suite": m.get("suite"),
            "path": rel(dy.parent),
            "top_module": m.get("top_module"),
            "circuit_type": m.get("circuit_type"),
            "golden_tb": bool(as_list(m.get("golden_tb"))),
            "mutants": len(as_list(m.get("mutants"))),
            "aliases": as_list(m.get("aliases")),
        })
    out = yaml.safe_dump({"generated_by": "scripts/standardize.py index", "designs": entries},
                         sort_keys=False)
    if args.apply:
        (DESIGNS / "manifest.yaml").write_text(out)
        print(f"wrote designs/manifest.yaml ({len(entries)} designs)")
    else:
        print(out + "\n(dry run; pass --apply to write)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import", help="copy a raw dataset into designs/<suite>/")
    p.add_argument("raw_dir")
    p.add_argument("--importer", required=True)
    p.add_argument("--suite", required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_import)
    p = sub.add_parser("check", help="validate designs/ and experiment configs")
    p.add_argument("--no-configs", action="store_true")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("index", help="regenerate designs/manifest.yaml")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_index)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
