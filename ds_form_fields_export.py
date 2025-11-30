#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_form_fields_export.py
------------------------
Ekstraherer ALLE form-felter fra en Zoho .ds-fil og eksporterer dem til JSON.

Design:
- Vi leser KUN den første `forms { ... }`-seksjonen i .ds-filen.
  (I din dump ligger fullstendige form-definisjoner der, senere `forms`-blokker
   har kun overrides som label placement osv.)
- For hver `form <Navn> { ... }` finner vi alle felt som har struktur:

      FeltNavn
      (
          ... konfig ...
      )

Per felt får du bl.a.:
- form_name
- field_name
- display_name       (fra displayname = "...")
- type               (fra type = ...)
- required           (true/false, fra required = true)
- default_value      (fra default = "...")
- lookup_details     (lookup-form osv. der det er relevant)
- order              (rekkefølge innen form, 1-basert, per felt-header)
- config             (rå tekst fra feltets parentesblokk)
- source_file
- start_line         (linjenummer der felt-headeren står)
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


def extract_paren_block_local(s: str, open_idx: int) -> Tuple[str, int, int]:
    """
    Som extract_brace_block, men for parenteser og innenfor en lokal streng `s`.
    Returnerer (body, body_start_idx, body_end_idx) relativt til `s`.
    """
    if s[open_idx] != "(":
        open_idx = s.find("(", open_idx)
        if open_idx == -1:
            raise ValueError("Fant ikke '(' ved forventet posisjon")
    depth = 0
    for i in range(open_idx, len(s)):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return s[open_idx + 1 : i], open_idx + 1, i
    raise ValueError("Ubalanserte parenteser fra posisjon %d" % open_idx)


def find_first_forms_section(text: str) -> Tuple[str, int, int]:
    """
    Finn den FØRSTE `forms { ... }`-seksjonen og returner (body, start_abs, end_abs).
    Det er her fullstendige form-definisjoner ligger i din .ds-fil.
    """
    m = re.search(r"^\s*forms\s*$", text, re.MULTILINE)
    if not m:
        raise ValueError("Fant ingen 'forms'-seksjon i .ds-filen")
    brace_idx = text.find("{", m.end())
    if brace_idx == -1:
        raise ValueError("Fant ikke '{' etter 'forms'")
    body, start, end = extract_brace_block(text, brace_idx)
    return body, start, end


FORM_HEADER_RE = re.compile(r"^\s*form\s+(\w+)", re.MULTILINE)

# Linje som kun består av et navn:   FeltNavn
FIELD_HEADER_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", re.MULTILINE)


def parse_form_fields(text: str, source_file: str = "") -> List[Dict[str, Any]]:
    """
    Parse alle form-felter fra .ds-teksten (kun første forms-blokk)
    og returner en flat liste med felt-dicts.
    """
    all_fields: List[Dict[str, Any]] = []

    forms_body, forms_start, forms_end = find_first_forms_section(text)

    for m_form in FORM_HEADER_RE.finditer(forms_body):
        form_name = m_form.group(1)
        form_header_abs = forms_start + m_form.start()

        # Finn '{' som starter selve form-blokken
        brace_idx_abs = text.find("{", form_header_abs, forms_end)
        if brace_idx_abs == -1:
            continue

        form_body, form_start, form_end = extract_brace_block(text, brace_idx_abs)

        order = 0

        # Iterer over alle felt-headere inni form_body
        for m_field in FIELD_HEADER_RE.finditer(form_body):
            field_name = m_field.group(1)
            header_local_idx = m_field.start()
            header_abs_idx = form_start + header_local_idx

            # Finn neste '(' etter headeren i form_body
            search_from = m_field.end()
            open_paren_local = form_body.find("(", search_from)
            if open_paren_local == -1:
                # Ingen konfig-blokk – hopp over (kan være noe annet, f.eks. "on load")
                continue

            try:
                config_body, c_start_local, c_end_local = extract_paren_block_local(
                    form_body, open_paren_local
                )
            except ValueError:
                # Ubalanserte parenteser – hopp over dette feltet
                continue

            order += 1

            # Parse ut noen vanlige config-verdier
            config = config_body.strip()

            display_name = None
            ftype = None
            required = False
            default_value = None
            lookup_details: Dict[str, str] = {}

            # displayname = "..."
            m_disp = re.search(r'displayname\s*=\s*"([^"]*)"', config, re.IGNORECASE)
            if m_disp:
                display_name = m_disp.group(1)

            # type = ...
            m_type = re.search(r'\btype\s*=\s*([A-Za-z0-9_]+)', config)
            if m_type:
                ftype = m_type.group(1)

            # required = true
            if re.search(r'\brequired\s*=\s*true', config, re.IGNORECASE):
                required = True

            # default = "..."
            m_def = re.search(r'\bdefault\s*=\s*"([^"]*)"', config, re.IGNORECASE)
            if m_def:
                default_value = m_def.group(1)

            # lookup-form (for relasjonsfelter)
            m_lf = re.search(r'\bform\s*=\s*([A-Za-z0-9_]+)', config)
            if m_lf:
                lookup_details["form"] = m_lf.group(1)

            all_fields.append(
                {
                    "form_name": form_name,
                    "field_name": field_name,
                    "display_name": display_name,
                    "type": ftype,
                    "required": required,
                    "default_value": default_value,
                    "lookup_details": lookup_details or None,
                    "order": order,
                    "config": config,
                    "source_file": os.path.basename(source_file) if source_file else "",
                    "start_line": char_to_line(text, header_abs_idx),
                }
            )

    return all_fields


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksporter form-felter fra .ds-fil til JSON."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Sti til .ds-filen",
    )
    parser.add_argument(
        "--out",
        default="form_fields.json",
        help="Filnavn for resultat (default: form_fields.json)",
    )
    args = parser.parse_args()

    text = read_text(args.file)
    fields = parse_form_fields(text, source_file=args.file)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(fields, f, ensure_ascii=False, indent=2)

    print(f"{len(fields)} form-felter eksportert til {args.out}")


if __name__ == "__main__":
    main()
