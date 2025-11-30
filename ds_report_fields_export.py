#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_report_fields_export.py
--------------------------
Ekstraherer ALLE felter (kolonner) for alle rapporter (views) i en Zoho .ds-fil
og eksporterer resultatet som JSON.

Per felt får du:
- report_name    : navnet på rapporten dette feltet tilhører
- field_name     : uttrykket før ev. `as "..."` (f.eks. Tiltak, Akt_r.ID)
- display_name   : teksten i `as "..."` hvis satt, ellers None
- expression     : samme som field_name (lagt inn eksplisitt for ev. senere utvidelser)
- order          : løpenummer innen rapporten (1-basert)
- config         : rå tekst for konfigurasjonsblokken i parentes, hvis den finnes
- source_file    : .ds-filnavn
- start_line     : linjenummer i .ds-filen der feltet er definert

Formålet er å kunne koble dette mot `reports.json` via report_name, og bruke
feltene i videre analyser/visualisering i Zoho/KI.
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


def extract_paren_block(text: str, open_idx: int) -> Tuple[str, int, int]:
    """
    Gitt indeks til en '(' i `text`, returner innholdet inni parentesblokken,
    samt start- og sluttindeks (eksklusiv slutt). Håndterer nestede parenteser.
    """
    if text[open_idx] != "(":
        raise ValueError("extract_paren_block: expected '(' at position %d" % open_idx)
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i], open_idx + 1, i
    raise ValueError("Unbalanced parentheses starting at %d" % open_idx)


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

# Feltlinje:   FeltNavn as "Visningsnavn"
# eller:      FeltNavn
FIELD_RE = re.compile(
    r'^([A-Za-z0-9_.]+)(?:\s+as\s+"([^"]*)")?$'
)


def parse_fields_from_rows_block(
    text: str,
    rows_body: str,
    rows_start_abs: int,
    report_name: str,
    source_file: str,
) -> List[Dict[str, Any]]:
    """
    Parse alle feltlinjer inni `show ... rows from ... ( ... )`-blokken
    og returner en liste med dicts for hvert felt.
    """
    fields: List[Dict[str, Any]] = []

    # Vi vil både kunne finne linjenummer (globalt) og holde orden på rekkefølge.
    lines = rows_body.splitlines(keepends=True)
    cursor = 0  # posisjon inne i rows_body (0-basert)
    idx = 0
    order = 0

    while idx < len(lines):
        line = lines[idx]
        line_stripped = line.strip()

        line_abs_start = rows_start_abs + cursor

        # Oppdater cursor for neste runde allerede nå
        cursor += len(line)

        # Hopp over tomme linjer og rene parentes-linjer
        if not line_stripped or line_stripped in ("(", ")"):
            idx += 1
            continue

        m_field = FIELD_RE.match(line_stripped)
        if not m_field:
            idx += 1
            continue

        expr = m_field.group(1)
        display_name = m_field.group(2) if m_field.group(2) is not None else None

        # Sjekk om neste linjer utgjør en konfig-blokk i parentes
        config = None
        j = idx + 1

        # Hopp over tomme linjer mellom header og eventuell '('
        while j < len(lines) and lines[j].strip() == "":
            cursor += len(lines[j])
            j += 1

        if j < len(lines) and lines[j].lstrip().startswith("("):
            # Start på konfig-blokk
            depth = 0
            config_lines: List[str] = []
            k = j
            # Merk: siden cursor allerede er oppdatert frem til idx-linjen,
            # justerer vi ikke cursor her (vi trenger ikke posisjon inni config).
            while k < len(lines):
                l2 = lines[k]
                depth += l2.count("(")
                depth -= l2.count(")")
                config_lines.append(l2.rstrip("\n"))
                k += 1
                if depth <= 0 and "(" in "".join(config_lines):
                    break
            config = "\n".join(config_lines).strip()
            idx = k
        else:
            idx += 1

        order += 1

        fields.append(
            {
                "report_name": report_name,
                "field_name": expr,
                "display_name": display_name,
                "expression": expr,
                "order": order,
                "config": config,
                "source_file": os.path.basename(source_file) if source_file else "",
                "start_line": char_to_line(text, line_abs_start),
            }
        )

    return fields


def parse_report_fields(text: str, source_file: str = "") -> List[Dict[str, Any]]:
    """
    Parse alle rapporter og feltene deres fra .ds-teksten,
    og returner en flat liste med felt-dicts.
    """
    all_fields: List[Dict[str, Any]] = []

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

            # Finn "show all rows from ..." eller "show rows from ..."
            m_rows = re.search(
                r"show\s+all\s+rows\s+from\s+([A-Za-z0-9_]+)|show\s+rows\s+from\s+([A-Za-z0-9_]+)",
                report_body,
            )
            if not m_rows:
                # F.eks. summary/pivot uten eksplisitt rows-definisjon – hopp over i denne runden
                continue

            # Finn '(' etter matchen – dette er starten på feltblokken
            rel_idx = m_rows.end()
            open_paren_rel = report_body.find("(", rel_idx)
            if open_paren_rel == -1:
                continue

            open_paren_abs = report_start + open_paren_rel
            rows_body, rows_start_abs, rows_end_abs = extract_paren_block(text, open_paren_abs)

            fields = parse_fields_from_rows_block(
                text=text,
                rows_body=rows_body,
                rows_start_abs=rows_start_abs,
                report_name=report_name,
                source_file=source_file,
            )
            all_fields.extend(fields)

    return all_fields


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksporter alle rapportfelter (kolonner) fra .ds-fil til JSON."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Sti til .ds-filen",
    )
    parser.add_argument(
        "--out",
        default="report_fields.json",
        help="Filnavn for resultat (default: report_fields.json)",
    )
    args = parser.parse_args()

    text = read_text(args.file)
    fields = parse_report_fields(text, source_file=args.file)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(fields, f, ensure_ascii=False, indent=2)

    print(f"{len(fields)} rapportfelt eksportert til {args.out}")


if __name__ == "__main__":
    main()
