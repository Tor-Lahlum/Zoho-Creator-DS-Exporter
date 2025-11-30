#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_form_workflows_with_code_export.py
-------------------------------------
Lister alle *form workflows* i en Zoho .ds-fil og eksporterer resultatet som JSON,
inkludert Deluge-kode inni workflowene.

Per workflow får du blant annet:
- workflow_name      : internt navn i .ds-filen
- display_name       : visningsnavn etter `as "..."`
- type               : forventes å være "form"
- form_name          : navnet på skjemaet (form = ...)
- record_event       : verdi fra `record event = ...`
- events             : liste med event-objekter
    - event_type     : f.eks. "on load", "on validate", "on user input"
    - field          : felt ved "on user input of <Felt>", ellers None
    - actions        : liste over actions
        - action_type : "custom_deluge_script"
        - script      : Deluge-koden inni `custom deluge script ( ... )`
- source_file        : filnavn til .ds-filen
- start_line         : linjenummer der workflow-headeren starter
- end_line           : linjenummer der workflow-blokken slutter
- start_position     : tegnindeks (0-basert) til første tegn INNE i `{`-blokken
- end_position       : tegnindeks (0-basert) til avsluttende `}` for workflow-blokken
- body               : hele innholdet inni `{ ... }` for workflowen
- full_source        : header + hele workflow-blokken slik den står i .ds-filen

JSON-strukturen kan senere importeres i Zoho Creator, og Deluge-koden kan legges
i multiline-strengfelt.
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
                # i peker på '}' når depth går til 0
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


def find_workflow_form_section(text: str) -> Tuple[str, int, int]:
    """
    Finn `workflow { ... form { ... } ... }`-seksjonen og returner innholdet
    inni `form { ... }` pluss start-/sluttindekser relativt til hele teksten.
    """
    for m_wf in re.finditer(r"^\s*workflow\s*$", text, re.MULTILINE):
        brace_idx = text.find("{", m_wf.end())
        if brace_idx == -1:
            continue
        try:
            wf_body, wf_start, wf_end = extract_brace_block(text, brace_idx)
        except ValueError:
            continue

        m_form = re.search(r"^\s*form\s*$", wf_body, re.MULTILINE)
        if not m_form:
            continue

        brace_in_wf = wf_body.find("{", m_form.end())
        if brace_in_wf == -1:
            continue

        form_open_abs = wf_start + brace_in_wf
        form_body, form_start, form_end = extract_brace_block(text, form_open_abs)
        return form_body, form_start, form_end

    raise ValueError("No workflow section with form-block found")


# Header-linje:   Navn as "Visningsnavn"
HEADER_RE = re.compile(
    r'^\s*(?P<name>\w+)\s+as\s+"(?P<display>[^"]+)"\s*$',
    re.MULTILINE,
)

# Event-linje:    on load / on validate / on user input of Felt
EVENT_HEADER_RE = re.compile(r"^\s*on\s+(.+?)\s*$", re.MULTILINE)


def parse_form_workflows_with_code(text: str, source_file: str = "") -> List[Dict[str, Any]]:
    """
    Parse alle form-workflows fra .ds-tekst og returner som en liste med dicts.
    Inkluderer Deluge-kode fra `custom deluge script ( ... )`.
    """
    form_body, form_start_abs, form_end_abs = find_workflow_form_section(text)

    workflows: List[Dict[str, Any]] = []

    # Vi bruker original-tekst for linjenumre og blokkgrenser,
    # men finner workflow-headerne relativt til form_body.
    for m in HEADER_RE.finditer(form_body):
        wf_name = m.group("name")
        display_name = m.group("display")
        header_rel_start = m.start()
        header_abs_start = form_start_abs + header_rel_start

        # Finn '{' som starter selve workflow-blokken
        brace_idx_abs = text.find("{", header_abs_start)
        if brace_idx_abs == -1 or brace_idx_abs > form_end_abs:
            continue

        wf_block_body, wf_block_start, wf_block_end = extract_brace_block(text, brace_idx_abs)

        # Metadata fra workflow-body
        type_match = re.search(r"\btype\s*=\s*([^\n]+)", wf_block_body)
        form_match = re.search(r"\bform\s*=\s*([^\n]+)", wf_block_body)
        event_match = re.search(r"\brecord event\s*=\s*([^\n]+)", wf_block_body)

        wf_type = type_match.group(1).strip() if type_match else ""
        form_name = form_match.group(1).strip() if form_match else ""
        record_event = event_match.group(1).strip() if event_match else ""

        # Parse events inni workflow-blokken
        events: List[Dict[str, Any]] = []
        for ev in EVENT_HEADER_RE.finditer(wf_block_body):
            raw = ev.group(1).strip()

            # Event-type og felt
            if raw.lower().startswith("user input of"):
                # on user input of Field
                parts = raw.split("of", 1)
                event_type = "on " + parts[0].strip()   # "on user input"
                field = parts[1].strip() if len(parts) > 1 else None
            else:
                event_type = "on " + raw
                field = None

            # Finn klammeblokk etter event-headeren
            # Vi må operere på fulltekst for å få riktige klammegrenser.
            ev_search_from = wf_block_start + ev.end()
            brace_idx_abs_ev = text.find("{", ev_search_from, wf_block_end)
            if brace_idx_abs_ev == -1:
                continue

            ev_body, ev_body_start, ev_body_end = extract_brace_block(text, brace_idx_abs_ev)

            # Inni event-body finner vi actions/custom deluge script
            actions: List[Dict[str, Any]] = []

            pos = 0
            marker = "custom deluge script"
            while True:
                idx = ev_body.find(marker, pos)
                if idx == -1:
                    break

                open_paren = ev_body.find("(", idx)
                if open_paren == -1:
                    break

                try:
                    script_body, p_start, p_end = extract_paren_block(ev_body, open_paren)
                except ValueError:
                    # Ubalanserte parenteser – hopp over denne action
                    break

                actions.append(
                    {
                        "action_type": "custom_deluge_script",
                        "script": script_body.strip(),
                    }
                )
                pos = p_end + 1

            events.append(
                {
                    "event_type": event_type,
                    "field": field,
                    "actions": actions,
                }
            )

        full_source = text[header_abs_start : wf_block_end + 1]

        workflows.append(
            {
                "workflow_name": wf_name,
                "display_name": display_name,
                "type": wf_type,
                "form_name": form_name,
                "record_event": record_event,
                "events": events,

                # posisjoner i hele .ds-teksten:
                "start_position": wf_block_start,
                "end_position": wf_block_end,

                # hele workflow-innholdet:
                "body": wf_block_body,
                "full_source": full_source,

                # metadata:
                "source_file": os.path.basename(source_file) if source_file else "",
                "start_line": char_to_line(text, header_abs_start),
                "end_line": char_to_line(text, wf_block_end),
            }
        )

    return workflows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksporter form-workflows fra .ds-fil til JSON (inkl. Deluge-kode)."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Sti til .ds-filen",
    )
    parser.add_argument(
        "--out",
        default="form_workflows_with_code.json",
        help="Filnavn for resultat (default: form_workflows_with_code.json)",
    )
    args = parser.parse_args()

    text = read_text(args.file)
    workflows = parse_form_workflows_with_code(text, source_file=args.file)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(workflows, f, ensure_ascii=False, indent=2)

    print(f"{len(workflows)} form-workflows eksportert til {args.out}")


if __name__ == "__main__":
    main()
