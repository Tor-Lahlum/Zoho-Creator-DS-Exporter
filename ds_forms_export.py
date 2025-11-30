#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_forms_export.py
------------------
Eksporterer ALLE forms (skjema) fra en Zoho .ds-fil til en samlet JSON-fil.

VIKTIG:
I mange .ds-filer finnes forms i flere `forms { ... }`-blokker (f.eks. egne blokker
for label placement/overrides). Dette scriptet sørger for at hver `form_name` kun
forekommer én gang, ved å beholde varianten med størst form-body
(den mest komplette definisjonen).

Per form får du:
- form_name        : internt navn i .ds-filen (etter `form <Navn>`)
- display_name     : displayname i Creator (hvis satt)
- description      : description = "..." (hvis satt)
- success_message  : success message = "..." (hvis satt)
- source_file      : .ds-filnavn
- start_line       : linjenummer der form-definisjonen starter
- end_line         : linjenummer der form-blokken slutter
- start_position   : tegnindeks (0-basert) for første tegn inne i form-blokken `{`
- end_position     : tegnindeks (0-basert) for avsluttende `}` i form-blokken
- body             : hele innholdet inni `{ ... }` for form-definisjonen
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
        open_idx = text.find("{", open_idx)
        if open_idx == -1:
            raise ValueError("extract_brace_block: fant ikke '{'")
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


def find_forms_sections(text: str) -> List[Tuple[str, int, int]]:
    """
    Finn alle `forms { ... }`-seksjoner og returner en liste med
    (body, start_abs, end_abs) for hver.
    """
    sections: List[Tuple[str, int, int]] = []
    for m in re.finditer(r"^\s*forms\s*$", text, re.MULTILINE):
        brace_idx = text.find("{", m.end())
        if brace_idx == -1:
            continue
        try:
            body, start, end = extract_brace_block(text, brace_idx)
        except ValueError:
            continue
        sections.append((body, start, end))
    return sections


FORM_HEADER_RE = re.compile(r"^\s*form\s+(\w+)", re.MULTILINE)


def parse_forms(text: str, source_file: str = "") -> List[Dict[str, Any]]:
    """
    Parse alle form-definisjoner fra .ds-teksten og returner en liste med dicts.
    Hvis samme form finnes i flere `forms { ... }`-blokker, beholder vi bare
    varianten med størst body (full definisjon fremfor enkle overrides).
    """
    forms_by_name: Dict[str, Dict[str, Any]] = {}

    for body, body_start, body_end in find_forms_sections(text):
        for m in FORM_HEADER_RE.finditer(body):
            form_name = m.group(1)
            header_abs_start = body_start + m.start()

            # Finn '{' som starter selve form-blokken
            brace_idx_abs = text.find("{", header_abs_start, body_end)
            if brace_idx_abs == -1:
                continue

            form_body, form_start, form_end = extract_brace_block(text, brace_idx_abs)

            # displayname (case-insensitivt)
            m_disp = re.search(r'(?i)\bdisplayname\s*=\s*"([^"]*)"', form_body)
            display_name = m_disp.group(1) if m_disp else ""

            # description (case-insensitivt)
            m_desc = re.search(r'(?i)\bdescription\s*=\s*"([^"]*)"', form_body)
            description = m_desc.group(1) if m_desc else ""

            # success message (case-insensitivt, med mellomrom)
            m_success = re.search(r'(?i)\bsuccess message\s*=\s*"([^"]*)"', form_body)
            success_message = m_success.group(1) if m_success else ""

            rec = {
                "form_name": form_name,
                "display_name": display_name,
                "description": description,
                "success_message": success_message,
                "source_file": os.path.basename(source_file) if source_file else "",
                "start_line": char_to_line(text, header_abs_start),
                "end_line": char_to_line(text, form_end),
                "start_position": form_start,
                "end_position": form_end,
                "body": form_body,
            }

            # Deduplisering per form_name – behold størst body
            prev = forms_by_name.get(form_name)
            if prev is None or len(rec["body"]) > len(prev["body"]):
                forms_by_name[form_name] = rec

    return list(forms_by_name.values())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksporter alle forms fra .ds-fil til JSON (struktur, deduplisert per form_name)."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Sti til .ds-filen",
    )
    parser.add_argument(
        "--out",
        default="forms.json",
        help="Filnavn for resultat (default: forms.json)",
    )
    args = parser.parse_args()

    text = read_text(args.file)
    forms = parse_forms(text, source_file=args.file)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(forms, f, ensure_ascii=False, indent=2)

    print(f"{len(forms)} form(er) eksportert til {args.out}")


if __name__ == "__main__":
    main()
