#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_report_workflows_with_code_export.py
---------------------------------------
Ekstraherer alle report-workflows (custom actions på rapporter/views) fra en Zoho .ds-fil
og eksporterer resultatet som JSON.

NB: Selve Deluge-koden ligger normalt i funksjoner som refereres via `workflow = ...`.
Dette scriptet henter derfor ikke Deluge-kode, men full konfigurasjon av custom actions
(sluttbruker-knappene på rapportene).

Per rapport:
- report_name        : internt rapportnavn
- report_type        : default list | list | summary | pivotchart | ...
- display_name       : displayname på rapporten (hvis satt)
- actions            : liste over custom actions
    - action_label   : knappetekst/label
    - workflow_name  : navnet etter `workflow =`
    - settings       : øvrige key = value-linjer i action-konfigen
    - start_line     : linjenummer der action starter
    - end_line       : linjenummer der action slutter
    - start_position : tegnindeks (0-basert) i hele .ds-teksten der action starter
    - end_position   : tegnindeks (0-basert) der action-konfigen slutter
    - body           : innholdet inni parentesene til action-konfigen
    - full_source    : hele custom action-definisjonen for denne action
- source_file        : filnavn til .ds-filen
- start_line         : linjenummer der rapporten starter
- end_line           : linjenummer der rapportblokken slutter
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


def parse_report_workflows_with_code(text: str, source_file: str = "") -> List[Dict[str, Any]]:
    """
    Parse alle rapporter med custom actions (report-workflows) fra .ds-tekst
    og returner som en liste med dicts.
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

            actions: List[Dict[str, Any]] = []

            # ---------------------------------------------------
            # STEG 1: custom actions ( "Label" ( ... ) )
            # ---------------------------------------------------
            pos = 0
            marker = "custom actions"
            while True:
                idx = report_body.find(marker, pos)
                if idx == -1:
                    break

                # Finn '(' etter "custom actions"
                open_paren_rel = report_body.find("(", idx)
                if open_paren_rel == -1:
                    break

                custom_body, custom_start_rel, custom_end_rel = extract_paren_block(
                    report_body, open_paren_rel
                )
                custom_abs_base = report_start + custom_start_rel

                # Linjer som starter med "Label" ( ... )
                for mm in re.finditer(r'^\s*"(?P<label>[^"]+)"\s*\(', custom_body, re.MULTILINE):
                    label = mm.group("label")

                    # Finn config-blokken rett etter labelen: "(" ... ")"
                    open_paren_for_label = custom_body.find("(", mm.end() - 1)
                    if open_paren_for_label == -1:
                        continue

                    conf_body, conf_start_rel, conf_end_rel = extract_paren_block(
                        custom_body, open_paren_for_label
                    )

                    action_abs_start = custom_abs_base + mm.start()
                    action_abs_end = custom_abs_base + conf_end_rel

                    # Hent workflow-navn
                    m_wf = re.search(r"\bworkflow\s*=\s*([A-Za-z0-9_]+)", conf_body)
                    workflow_name = m_wf.group(1) if m_wf else ""

                    # Hent øvrige innstillinger (key = value per linje)
                    settings: Dict[str, str] = {}
                    for mset in re.finditer(r"([A-Za-z_ ]+?)\s*=\s*([^\n]+)", conf_body):
                        key = mset.group(1).strip()
                        val = mset.group(2).strip()
                        if key.lower() == "workflow":
                            continue
                        settings[key] = val

                    full_source = text[action_abs_start : action_abs_end + 1]

                    actions.append(
                        {
                            "action_label": label,
                            "workflow_name": workflow_name,
                            "settings": settings,
                            "start_line": char_to_line(text, action_abs_start),
                            "end_line": char_to_line(text, action_abs_end),
                            "start_position": action_abs_start,
                            "end_position": action_abs_end,
                            "body": conf_body,
                            "full_source": full_source,
                        }
                    )

                pos = custom_end_rel + 1

            # ---------------------------------------------------
            # STEG 2: inline `custom action "Label" ( ... )`
            # ---------------------------------------------------
            INLINE_RE = re.compile(
                r'\bcustom action\s+"(?P<label>[^"]+)"\s*\(', re.MULTILINE
            )

            for mm in INLINE_RE.finditer(report_body):
                label = mm.group("label")

                # Finn "(" etter matchen
                open_paren_rel = report_body.find("(", mm.end() - 1)
                if open_paren_rel == -1:
                    continue

                conf_body, conf_start_rel, conf_end_rel = extract_paren_block(
                    report_body, open_paren_rel
                )

                action_abs_start = report_start + mm.start()
                action_abs_end = report_start + conf_end_rel

                # Workflow-navn
                m_wf = re.search(r"\bworkflow\s*=\s*([A-Za-z0-9_]+)", conf_body)
                workflow_name = m_wf.group(1) if m_wf else ""

                # Øvrige settings
                settings: Dict[str, str] = {}
                for mset in re.finditer(r"([A-Za-z_ ]+?)\s*=\s*([^\n]+)", conf_body):
                    key = mset.group(1).strip()
                    val = mset.group(2).strip()
                    if key.lower() == "workflow":
                        continue
                    settings[key] = val

                full_source = text[action_abs_start : action_abs_end + 1]

                actions.append(
                    {
                        "action_label": label,
                        "workflow_name": workflow_name,
                        "settings": settings,
                        "start_line": char_to_line(text, action_abs_start),
                        "end_line": char_to_line(text, action_abs_end),
                        "start_position": action_abs_start,
                        "end_position": action_abs_end,
                        "body": conf_body,
                        "full_source": full_source,
                    }
                )

            if actions:
                reports.append(
                    {
                        "report_name": report_name,
                        "report_type": report_type,
                        "display_name": display_name,
                        "actions": actions,
                        "source_file": os.path.basename(source_file) if source_file else "",
                        "start_line": char_to_line(text, header_abs_start),
                        "end_line": char_to_line(text, report_end),
                    }
                )

    return reports


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksporter report-workflows (custom actions) fra .ds-fil til JSON (inkl. action-konfig)."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Sti til .ds-filen",
    )
    parser.add_argument(
        "--out",
        default="report_workflows_with_code.json",
        help="Filnavn for resultat (default: report_workflows_with_code.json)",
    )
    args = parser.parse_args()

    text = read_text(args.file)
    reports = parse_report_workflows_with_code(text, source_file=args.file)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)

    print(f"{len(reports)} rapport(er) med custom actions eksportert til {args.out}")


if __name__ == "__main__":
    main()
