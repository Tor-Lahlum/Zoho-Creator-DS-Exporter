import argparse
import os
import subprocess
import sys
from pathlib import Path


OUTPUT_FILES = {
    "ds_forms_export.py": "forms.json",
    "ds_form_fields_export.py": "form_fields.json",
    "ds_form_workflows_export.py": "form_workflows.json",
    "ds_functions_export.py": "functions.json",
    "ds_pages_export.py": "pages.json",
    "ds_page_components_export.py": "page_components.json",
    "ds_reports_export.py": "reports.json",
    "ds_report_fields_export.py": "report_fields.json",
    "ds_report_workflows_export.py": "report_workflows.json",
}


def find_default_ds_file(base_dir: Path) -> Path:
    ds_files = sorted(base_dir.glob("*.ds"))

    if len(ds_files) == 1:
        return ds_files[0]

    if len(ds_files) == 0:
        raise FileNotFoundError(
            f"Fant ingen .ds-filer i {base_dir}. Oppgi --ds eksplisitt."
        )

    names = ", ".join(ds_file.name for ds_file in ds_files)
    raise FileNotFoundError(
        f"Fant flere .ds-filer i {base_dir}: {names}. Oppgi --ds eksplisitt."
    )


def build_command(script_name: str, script_path: Path, ds_file: Path, out_file: Path) -> list[str]:
    if script_name == "ds_form_fields_export.py":
        return [sys.executable, str(script_path), str(ds_file), str(out_file)]

    if script_name == "ds_report_workflows_export.py":
        return [sys.executable, str(script_path), "--ds", str(ds_file), "--out", str(out_file)]

    return [sys.executable, str(script_path), "--file", str(ds_file), "--out", str(out_file)]


def run_script(script_name: str, ds_file: Path, outdir: Path, base_dir: Path) -> bool:
    script_path = base_dir / script_name

    if not script_path.exists():
        print(f"SKIPPET (finnes ikke): {script_name}")
        return False

    out_file = outdir / OUTPUT_FILES[script_name]
    print(f"Kjorer: {script_name} -> {out_file}")

    cmd = build_command(script_name, script_path, ds_file, out_file)

    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"FEIL i {script_name}: {e}")
        return False


def main() -> None:
    base_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ds",
        help="Path til .ds-fil. Hvis utelatt brukes eneste .ds-fil i samme mappe som run_all_exports.py.",
    )
    parser.add_argument(
        "--outdir",
        help="Output-mappe. Standard er exports i samme mappe som run_all_exports.py.",
    )
    args = parser.parse_args()

    ds_file = Path(args.ds).resolve() if args.ds else find_default_ds_file(base_dir)
    outdir = Path(args.outdir).resolve() if args.outdir else base_dir / "exports"

    outdir.mkdir(parents=True, exist_ok=True)

    scripts = [
        "ds_forms_export.py",
        "ds_form_fields_export.py",
        "ds_form_workflows_export.py",
        "ds_functions_export.py",
        "ds_pages_export.py",
        "ds_page_components_export.py",
        "ds_reports_export.py",
        "ds_report_fields_export.py",
        "ds_report_workflows_export.py",
    ]

    ok = 0
    failed = 0

    print(f"DS-fil: {ds_file}")
    print(f"Output-mappe: {outdir}")

    for script_name in scripts:
        if run_script(script_name, ds_file, outdir, base_dir):
            ok += 1
        else:
            failed += 1

    print(f"\nFerdig. OK: {ok}, FEIL: {failed}")


if __name__ == "__main__":
    main()
