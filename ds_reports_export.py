#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_reports_export.py
--------------------
Eksporterer ALLE rapporter (views) fra en Zoho .ds-fil til en samlet JSON-fil.

Per rapport får du:
- report_name        : internt rapportnavn
- report_type        : default list | list | summary | pivotchart | ...
- display_name       : displayname på rapporten (hvis satt)
- base_form          : skjema det hentes rader fra (fra `show all rows from ...`)
- template           : ev. PDF-/layout-template (template = ...)
- print_template     : ev. print template (print template = ...)
- source_file        : .ds-filnavn
- start_line         : linjenummer der rapportdefinisjonen starter
- end_line           : linjenummer der rapportblokken slutter
- start_position     : tegnindeks (0-basert) for første tegn etter '{'
- end_position       : tegnindeks (0-basert) for avsluttende '}' i rapportblokken

Denne JSON-en er tenkt brukt som "struktur-oversikt" – uten Deluge-kode – og kan
enkelt analyseres videre eller kobles mot egne filer for workflows/functions.
"""

import re
import json
import argparse
import os
from typing import List, Dict, Any, Tuple


def read_text(path: str) -> str:
    """Les inn en tekstfil som UTF-8."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def char_to_line(text: str, idx: int) -> int:
    """Konverter tegnindeks til linjenummer (1-basert)."""
    return text.count("\n", 0, idx) + 1


def extract_brace_block(text: str, open_idx: int) -> Tuple[str, int, int]:
    """
    Gitt indeks til en '{' i `text`, returner innholdet inni blokken,
    samt start- og sluttindeks (eksklusiv slutt) for body.

    Returnerer (body, body_start_idx, body_end_idx) der:
    - body           : substring mellom '{' og '}'
    - body_start_idx : indeks til første tegn etter '{'
    - body_end_idx   : indeks til selve '}'-tegnet
    """
    if text[open_idx] != "{":
        raise ValueError("extract_brace_block: expected '{' at position %d" % open_idx)
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i], open_idx + 1, i
    raise ValueError("Unbalanced braces starting at %d" % open_idx)


def find_reports_sections(text: str) -> List[Tuple[str, int, int]]:
    """
    Finn alle `reports { ... }`-seksjoner og returner en liste med
    (body, start_abs, end_abs) for hver.
    """
    sections: List[Tuple[str, int, int]] = []
    for m in re.finditer(r"^\s*reports\s*$", text, re.MULTILINE):
        brace_idx = text.find("{", m.end())
        if brace_idx == -1:
            continue
        try:
            body, start, end = extract_brace_block(text, brace_idx)
        except ValueError:
            continue
        sections.append((body, start, end))
    return sections


REPORT_HEADER_RE = re.compile(
    r"^\s*(default\s+list|list|summary|pivotchart|pivot|chart|calendar|timeline|kanban|map|htmlview|tabular|matrix)\s+(\w+)",
    re.MULTILINE,
)


def parse_reports(text: str, source_file: str = "") -> List[Dict[str, Any]]:
    """
    Parse alle rapportdefinisjoner fra .ds-teksten og returner som liste med dicts.
    """
    reports: List[Dict[str, Any]] = []

    for body, body_start, body_end in find_reports_sections(text):
        for m in REPORT_HEADER_RE.finditer(body):
            report_type = m.group(1).strip()
            report_name = m.group(2)
            header_abs_start = body_start + m.start()

            # Finn '{' som starter selve rapportblokken
            brace_idx_abs = text.find("{", header_abs_start, body_end)
            if brace_idx_abs == -1:
                continue

            report_body, report_start, report_end = extract_brace_block(text, brace_idx_abs)

            # displayName / displayname (case-insensitivt)
            m_disp = re.search(r'(?i)\bdisplayname\s*=\s*"([^"]*)"', report_body)
            display_name = m_disp.group(1) if m_disp else ""

            # base_form: "show all rows from <FormName>" eller "show rows from ..."
            base_form = None
            m_form = re.search(r"show\s+all\s+rows\s+from\s+([A-Za-z0-9_]+)", report_body)
            if not m_form:
                m_form = re.search(r"show\s+rows\s+from\s+([A-Za-z0-9_]+)", report_body)
            if m_form:
                base_form = m_form.group(1)

            # template
            m_tmpl = re.search(r"\btemplate\s*=\s*([A-Za-z0-9_]+)", report_body)
            template = m_tmpl.group(1) if m_tmpl else None

            # print template
            m_ptmpl = re.search(r"\bprint template\s*=\s*([A-Za-z0-9_]+)", report_body)
            print_template = m_ptmpl.group(1) if m_ptmpl else None

            reports.append(
                {
                    "report_name": report_name,
                    "report_type": report_type,
                    "display_name": display_name,
                    "base_form": base_form,
                    "template": template,
                    "print_template": print_template,
                    "source_file": os.path.basename(source_file) if source_file else "",
                    "start_line": char_to_line(text, header_abs_start),
                    "end_line": char_to_line(text, report_end),
                    "start_position": report_start,
                    "end_position": report_end,
                }
            )

    return reports


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksporter alle rapporter fra .ds-fil til JSON (struktur, ikke Deluge-kode)."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Sti til .ds-filen",
    )
    parser.add_argument(
        "--out",
        default="reports.json",
        help="Filnavn for resultat (default: reports.json)",
    )
    args = parser.parse_args()

    text = read_text(args.file)
    reports = parse_reports(text, source_file=args.file)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)

    print(f"{len(reports)} rapport(er) eksportert til {args.out}")


if __name__ == "__main__":
    main()
