#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_form_workflows_export.py
---------------------------
Lister alle form workflows i en Zoho .ds-fil og eksporterer resultatet som JSON,
inkludert Deluge-kode inni workflowene.

Scriptet er robust mot .ds-filer som ikke har workflow/form-seksjon.
Da skrives en tom JSON-liste, og det rapporteres 0 workflows eksportert.
"""

import re
import json
import argparse
import os
from typing import List, Dict, Any, Tuple, Optional


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def char_to_line(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def extract_brace_block(text: str, open_idx: int) -> Tuple[str, int, int]:
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


def find_workflow_form_section(text: str) -> Optional[Tuple[str, int, int]]:
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

        try:
            form_body, form_start, form_end = extract_brace_block(text, form_open_abs)
        except ValueError:
            continue

        return form_body, form_start, form_end

    return None


HEADER_RE = re.compile(
    r'^\s*(?P<name>\w+)\s+as\s+"(?P<display>[^"]+)"\s*$',
    re.MULTILINE,
)

EVENT_HEADER_RE = re.compile(r"^\s*on\s+(.+?)\s*$", re.MULTILINE)


def parse_form_workflows_with_code(text: str, source_file: str = "") -> List[Dict[str, Any]]:
    section = find_workflow_form_section(text)
    if section is None:
        return []

    form_body, form_start_abs, form_end_abs = section
    workflows: List[Dict[str, Any]] = []

    for m in HEADER_RE.finditer(form_body):
        wf_name = m.group("name")
        display_name = m.group("display")
        header_abs_start = form_start_abs + m.start()

        brace_idx_abs = text.find("{", header_abs_start)
        if brace_idx_abs == -1 or brace_idx_abs > form_end_abs:
            continue

        try:
            wf_block_body, wf_block_start, wf_block_end = extract_brace_block(text, brace_idx_abs)
        except ValueError:
            continue

        type_match = re.search(r"\btype\s*=\s*([^\n]+)", wf_block_body)
        form_match = re.search(r"\bform\s*=\s*([^\n]+)", wf_block_body)
        event_match = re.search(r"\brecord event\s*=\s*([^\n]+)", wf_block_body)

        wf_type = type_match.group(1).strip() if type_match else ""
        form_name = form_match.group(1).strip() if form_match else ""
        record_event = event_match.group(1).strip() if event_match else ""

        events: List[Dict[str, Any]] = []
        for ev in EVENT_HEADER_RE.finditer(wf_block_body):
            raw = ev.group(1).strip()

            if raw.lower().startswith("user input of"):
                parts = raw.split("of", 1)
                event_type = "on " + parts[0].strip()
                field = parts[1].strip() if len(parts) > 1 else None
            else:
                event_type = "on " + raw
                field = None

            ev_search_from = wf_block_start + ev.end()
            brace_idx_abs_ev = text.find("{", ev_search_from, wf_block_end)
            if brace_idx_abs_ev == -1:
                continue

            try:
                ev_body, ev_body_start, ev_body_end = extract_brace_block(text, brace_idx_abs_ev)
            except ValueError:
                continue

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
                "start_position": wf_block_start,
                "end_position": wf_block_end,
                "body": wf_block_body,
                "full_source": full_source,
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
    parser.add_argument("--file", required=True, help="Sti til .ds-filen")
    parser.add_argument("--out", default="form_workflows.json", help="Filnavn for resultat (default: form_workflows.json)")
    args = parser.parse_args()

    text = read_text(args.file)
    workflows = parse_form_workflows_with_code(text, source_file=args.file)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(workflows, f, ensure_ascii=False, indent=2)

    print(f"{len(workflows)} form-workflows eksportert til {args.out}")


if __name__ == "__main__":
    main()
