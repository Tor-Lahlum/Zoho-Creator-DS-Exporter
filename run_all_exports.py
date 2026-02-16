#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import subprocess
import sys
from pathlib import Path

# Per script: (script, out_json, input_flag)
# Noen scripts bruker --ds, andre bruker --file (ser ut til å variere).
EXPORT_JOBS = [
    ("ds_form_fields_export.py",      "ex_form_fields.json",      "--ds"),
    ("ds_form_workflows_export.py",   "ex_form_workflows.json",   "--file"),
    ("ds_forms_export.py",            "ex_forms.json",            "--file"),
    ("ds_functions_export.py",        "ex_functions.json",        "--file"),
    ("ds_page_components_export.py",  "ex_page_components.json",  "--file"),
    ("ds_pages_export.py",            "ex_pages.json",            "--file"),
    ("ds_report_actions_export.py",   "ex_report_actions.json",   "--file"),
    ("ds_report_fields_export.py",    "ex_report_fields.json",    "--file"),
    ("ds_report_workflows_export.py", "ex_report_workflows.json", "--ds"),
    ("ds_reports_export.py",          "ex_reports.json",          "--file"),
]

def run_one(python_exe, script_path, ds_file, out_file, input_flag):
    cmd = [
        python_exe,
        str(script_path),
        input_flag, str(ds_file),
        "--out", str(out_file),
    ]
    print(f"\n==> Kjører: {' '.join(cmd)}")
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.stdout:
        print(p.stdout.rstrip())
    if p.returncode != 0:
        if p.stderr:
            print(p.stderr.rstrip(), file=sys.stderr)
        return p.returncode
    return 0

def main():
    parser = argparse.ArgumentParser(description="Kjør alle .ds export-script og produser JSON-filer.")
    parser.add_argument("--ds", default="Nasjonal_portefølje.ds", help="Sti til .ds-filen")
    parser.add_argument("--outdir", default=".", help="Output-mappe for JSON-filer")
    parser.add_argument("--python", default=sys.executable, help="Python executable")
    parser.add_argument("--continue-on-error", action="store_true", help="Fortsett selv om et script feiler")
    args = parser.parse_args()

    base_dir = Path.cwd()
    ds_file = Path(args.ds)
    out_dir = Path(args.outdir)

    if not ds_file.is_file():
        print(f"Fant ikke .ds-fil: {ds_file}", file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)

    missing = [s for (s, _, _) in EXPORT_JOBS if not (base_dir / s).is_file()]
    if missing:
        print("Mangler export-script:", file=sys.stderr)
        for s in missing:
            print(f"  - {s}", file=sys.stderr)
        return 2

    failures = []
    for script_name, out_name, input_flag in EXPORT_JOBS:
        rc = run_one(
            args.python,
            base_dir / script_name,
            ds_file,
            out_dir / out_name,
            input_flag
        )
        if rc != 0:
            failures.append((script_name, rc))
            if not args.continue_on_error:
                print(f"\nStoppet pga. feil i {script_name} (exit={rc})", file=sys.stderr)
                return rc

    if failures:
        print("\nFerdig med feil:", file=sys.stderr)
        for script_name, rc in failures:
            print(f"  - {script_name}: exit={rc}", file=sys.stderr)
        return 1

    print("\nFerdig: alle exports OK.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
