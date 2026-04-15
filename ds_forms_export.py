#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_forms_export_min.py
----------------------
Eksporterer forms (skjema) fra en Zoho Creator .ds-fil til JSON.

Per form eksporterer scriptet kun:
- form_name
- display_name        (kun form-nivå; hvis ikke satt => lik form_name)
- success_message
- mode                ("stateless" hvis `store data in zc = false`, ellers "normal")

Hvorfor denne logikken?
I .ds-filer finnes `displayname = "..."` både på form-nivå og inne i feltblokker.
Dette scriptet leser derfor *kun* form-headeren (før første feltblokk) når det
henter display_name/success_message/mode.
"""

import re
import json
import argparse
import os
from typing import List, Dict, Any, Tuple


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_brace_block(text: str, open_idx: int) -> Tuple[str, int, int]:
    """
    Returner (body, body_start_idx, body_end_idx) for en {...}-blokk.
    body_end_idx er indeksen til '}'-tegnet (ikke inkludert i body).
    """
    if text[open_idx] != "{":
        open_idx = text.find("{", open_idx)
        if open_idx == -1:
            raise ValueError("Fant ikke '{' fra angitt posisjon")
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i], open_idx + 1, i
    raise ValueError("Ubalanserte klammer fra posisjon %d" % open_idx)


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

# Heuristikk: første feltblokk ser typisk ut som:
#   FeltNavn
#   (
FIRST_FIELD_BLOCK_RE = re.compile(r"^\s*[A-Za-z_]\w*\s*\n\s*\(", re.MULTILINE)


def header_segment(form_body: str) -> str:
    """
    Returner kun "headeren" (før første feltblokk) for å unngå at vi plukker opp
    displayname fra felt/sections/print templates.
    """
    m = FIRST_FIELD_BLOCK_RE.search(form_body)
    return form_body[: m.start()] if m else form_body


def parse_forms(text: str, source_file: str = "") -> List[Dict[str, Any]]:
    """
    Parse alle form-definisjoner fra .ds-teksten.
    Hvis samme form finnes i flere `forms { ... }`-blokker, behold varianten med
    størst form-body (mest komplett definisjon).
    """
    forms_by_name: Dict[str, Dict[str, Any]] = {}

    for body, body_start, body_end in find_forms_sections(text):
        for m in FORM_HEADER_RE.finditer(body):
            form_name = m.group(1)

            # Finn '{' som starter selve form-blokken
            header_abs_start = body_start + m.start()
            brace_idx_abs = text.find("{", header_abs_start, body_end)
            if brace_idx_abs == -1:
                continue

            form_body, form_start, form_end = extract_brace_block(text, brace_idx_abs)

            hdr = header_segment(form_body)

            # Kun form-nivå metadata (i header-segmentet)
            m_disp = re.search(r'(?i)\bdisplayname\s*=\s*"([^"]*)"', hdr)
            display_name = m_disp.group(1) if m_disp else form_name

            m_success = re.search(r'(?i)\bsuccess message\s*=\s*"([^"]*)"', hdr)
            success_message = m_success.group(1) if m_success else ""

            m_store = re.search(r'(?i)\bstore data in zc\s*=\s*(true|false)\b', hdr)
            store_val = m_store.group(1).lower() if m_store else "true"
            mode = "stateless" if store_val == "false" else "normal"

            rec = {
                "form_name": form_name,
                "display_name": display_name,
                "success_message": success_message,
                "mode": mode,
                "source_file": os.path.basename(source_file) if source_file else "",
                "start_position": form_start,
                "end_position": form_end,
            }

            prev = forms_by_name.get(form_name)
            if prev is None or (rec["end_position"] - rec["start_position"]) > (prev["end_position"] - prev["start_position"]):
                forms_by_name[form_name] = rec

    # Returner stabil sortering for diff/lesbarhet
    return sorted(forms_by_name.values(), key=lambda x: x["form_name"].lower())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksporter forms fra Zoho Creator .ds til JSON (minimalt sett + stateless/normal)."
    )
    parser.add_argument("--file", required=True, help="Sti til .ds-filen")
    parser.add_argument("--out", default="forms_min.json", help="Output JSON (default: forms_min.json)")
    args = parser.parse_args()

    text = read_text(args.file)
    forms = parse_forms(text, source_file=args.file)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(forms, f, ensure_ascii=False, indent=2)

    print(f"{len(forms)} form(er) eksportert til {args.out}")


if __name__ == "__main__":
    main()
