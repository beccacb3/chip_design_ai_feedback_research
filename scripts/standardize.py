"""Put designs into one standard layout, and check that they follow it.

Every design lives in its own folder:

    designs/<group>/<name>/
        design.yaml     name, top_module, original_name
        spec.md         the natural-language specification
        rtl/            the design's Verilog files
        tb/             (optional) a reference testbench

Usage:
    python scripts/standardize.py check
    python scripts/standardize.py import-verilogeval <source_folder> <group> [--apply]

`import-verilogeval` only prints what it would do unless you add --apply.
"""

import re
import shutil
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGNS = REPO_ROOT / "designs"

# VerilogEval file names look like: Prob042_vector2_prompt.txt
#   group(1) = design name ("vector2"), group(2) = file role ("prompt")
VERILOGEVAL_FILE = re.compile(r"^Prob\d+_(.+)_(prompt|ref|test)\.(txt|sv|v)$")


def clean_name(name):
    """Make a consistent folder name: 'Vector2-Rev' -> 'vector2_rev'."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def module_names(verilog_file):
    """Return the names of the modules defined in a Verilog file."""
    return re.findall(r"^\s*module\s+(\w+)", verilog_file.read_text(), re.MULTILINE)


# --------------------------------------------------------------------- check


def check_design(folder):
    """Return a list of problems with one design folder."""
    problems = []

    if folder.name != clean_name(folder.name):
        problems.append(f"folder name should be '{clean_name(folder.name)}'")

    spec = folder / "spec.md"
    if not spec.exists():
        problems.append("missing spec.md")
    elif not spec.read_text().strip():
        problems.append("spec.md is empty")

    rtl_files = sorted((folder / "rtl").glob("*.*v"))
    if not rtl_files:
        problems.append("no .v or .sv files in rtl/")

    info_file = folder / "design.yaml"
    if not info_file.exists():
        problems.append("missing design.yaml")
        return problems

    info = yaml.safe_load(info_file.read_text())
    if info.get("name") != folder.name:
        problems.append(f"design.yaml name '{info.get('name')}' does not match folder name")

    modules = [m for f in rtl_files for m in module_names(f)]
    if rtl_files and info.get("top_module") not in modules:
        problems.append(f"top_module '{info.get('top_module')}' not found in rtl/ (found {modules})")

    return problems


def check():
    folders = sorted(p for p in DESIGNS.glob("*/*") if p.is_dir())
    total = 0
    for folder in folders:
        for problem in check_design(folder):
            print(f"{folder.relative_to(REPO_ROOT)}: {problem}")
            total += 1
    print(f"checked {len(folders)} design(s), found {total} problem(s)")
    return 1 if total else 0


# --------------------------------------------------------------------- import


def import_verilogeval(source, group, apply):
    # Group the source files by design name.
    designs = {}
    for path in sorted(Path(source).iterdir()):
        match = VERILOGEVAL_FILE.match(path.name)
        if match:
            name, role = clean_name(match.group(1)), match.group(2)
            designs.setdefault(name, {})[role] = path

    for name, files in designs.items():
        target = DESIGNS / group / name

        if "prompt" not in files or "ref" not in files:
            print(f"skip   {name}: needs both a _prompt and a _ref file")
            continue
        if target.exists():
            print(f"skip   {name}: {target.relative_to(REPO_ROOT)} already exists")
            continue

        print(f"import {files['prompt'].name} -> {target.relative_to(REPO_ROOT)}/")
        if not apply:
            continue

        (target / "rtl").mkdir(parents=True)
        shutil.copy(files["prompt"], target / "spec.md")
        shutil.copy(files["ref"], target / "rtl" / f"{name}.sv")
        if "test" in files:
            (target / "tb").mkdir()
            shutil.copy(files["test"], target / "tb" / f"{name}_tb.sv")

        # VerilogEval names its reference module "RefModule"; we record
        # whatever name is really in the file.
        info = {
            "name": name,
            "top_module": module_names(files["ref"])[0],
            "original_name": files["prompt"].name.removesuffix("_prompt.txt"),
        }
        (target / "design.yaml").write_text(yaml.safe_dump(info, sort_keys=False))

    if not apply:
        print("\nNothing was written. Add --apply to import.")
    return 0


def main():
    args = sys.argv[1:]
    if args == ["check"]:
        return check()
    if len(args) >= 3 and args[0] == "import-verilogeval":
        return import_verilogeval(args[1], args[2], apply="--apply" in args)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
