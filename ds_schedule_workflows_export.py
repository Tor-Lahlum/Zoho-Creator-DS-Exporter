#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_schedule_workflows_export.py
-------------------------------
Eksporterer schedule-workflows fra en Zoho Creator .ds-fil til JSON.

Støtter struktur som typisk ligger under:

workflow
{
    schedule
    {
        WorkflowNavn as "Visningsnavn"
        {
            type = schedule
            form = ...
            start = ...
            time zone = "..."
            on start
            {
                actions
                {
                    on load
                    (
                        ... Deluge-kode ...
                    )
                }
            }
        }
    }
}

Per workflow eksporteres bl.a.:
- workflow_name
- display_name
- type
- form_name
- start
- time_zone
- events[]
  - event_type
  - actions[]
    - action_type
    - script
- full_source
- start_line / end_line
"""

from __future__ import annotations

import re
import json
import argparse
import os
from typing import List, Dict, Any, Tuple, Optional


HEADER_RE = re.compile(r'^\s*(?P<name>\w+)\s+as\s+"(?P<display>[^"]+)"\s*$', re.MULTILINE)
EVENT_BLOCK_RE = re.compile(r'^\s*on\s+([A-Za-z ]+?)\s*$', re.MULTILINE)
KEY_VALUE_RE_TEMPLATE = r'(?im)^\s*{key}\s*=\s*(.+?)\s*$'


def read_text(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()



def char_to_line(text: str, idx: int) -> int:
    return text.count('\n', 0, idx) + 1



def extract_brace_block(text: str, open_idx: int) -> Tuple[str, int, int]:
    if text[open_idx] != '{':
        raise ValueError(f"Expected '{{' at position {open_idx}")

    depth = 0
    in_str = False
    str_char = ''
    escape = False

    for i in range(open_idx, len(text)):
        ch = text[i]

        if in_str:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == str_char:
                in_str = False
            continue

        if ch in ('"', "'"):
            in_str = True
            str_char = ch
            continue

        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i], open_idx + 1, i

    raise ValueError(f"Unbalanced braces starting at {open_idx}")



def extract_paren_block(text: str, open_idx: int) -> Tuple[str, int, int]:
    if text[open_idx] != '(':
        raise ValueError(f"Expected '(' at position {open_idx}")

    depth = 0
    in_str = False
    str_char = ''
    escape = False

    for i in range(open_idx, len(text)):
        ch = text[i]

        if in_str:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == str_char:
                in_str = False
            continue

        if ch in ('"', "'"):
            in_str = True
            str_char = ch
            continue

        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i], open_idx + 1, i

    raise ValueError(f"Unbalanced parentheses starting at {open_idx}")



def find_named_section(text: str, section_name: str, start_pos: int = 0) -> Optional[Tuple[str, int, int, int]]:
    pattern = re.compile(r'^\s*' + re.escape(section_name) + r'\s*$', re.MULTILINE)
    m = pattern.search(text, pos=start_pos)
    if not m:
        return None

    brace_idx = text.find('{', m.end())
    if brace_idx == -1:
        return None

    try:
        body, body_start, body_end = extract_brace_block(text, brace_idx)
    except ValueError:
        return None

    return body, body_start, body_end, m.start()



def find_schedule_section(text: str) -> Optional[Tuple[str, int, int]]:
    workflow_section = find_named_section(text, 'workflow')
    if workflow_section is None:
        return None

    workflow_body, workflow_start, workflow_end, _ = workflow_section
    schedule_match = re.search(r'^\s*schedule\s*$', workflow_body, re.MULTILINE)
    if not schedule_match:
        return None

    schedule_header_abs = workflow_start + schedule_match.start()
    brace_idx_abs = text.find('{', schedule_header_abs, workflow_end)
    if brace_idx_abs == -1:
        return None

    try:
        schedule_body, schedule_start, schedule_end = extract_brace_block(text, brace_idx_abs)
    except ValueError:
        return None

    return schedule_body, schedule_start, schedule_end



def extract_key_value(block_text: str, key: str) -> str:
    pattern = re.compile(KEY_VALUE_RE_TEMPLATE.format(key=re.escape(key)))
    m = pattern.search(block_text)
    return m.group(1).strip() if m else ''



def parse_actions(event_body: str) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    pos = 0

    while True:
        m = re.search(r'^\s*on\s+([A-Za-z ]+?)\s*$', event_body[pos:], re.MULTILINE)
        if not m:
            break

        action_name = m.group(1).strip()
        abs_rel_start = pos + m.start()
        paren_idx = event_body.find('(', pos + m.end())
        if paren_idx == -1:
            pos = pos + m.end()
            continue

        try:
            script_body, _, script_end = extract_paren_block(event_body, paren_idx)
        except ValueError:
            pos = pos + m.end()
            continue

        actions.append(
            {
                'action_type': 'on ' + action_name,
                'script': script_body.strip(),
            }
        )

        pos = script_end + 1
        if pos <= abs_rel_start:
            pos = abs_rel_start + 1

    return actions



def parse_schedule_workflows(text: str, source_file: str = '') -> List[Dict[str, Any]]:
    section = find_schedule_section(text)
    if section is None:
        return []

    schedule_body, schedule_start_abs, schedule_end_abs = section
    workflows: List[Dict[str, Any]] = []

    for m in HEADER_RE.finditer(schedule_body):
        wf_name = m.group('name')
        display_name = m.group('display')
        header_abs_start = schedule_start_abs + m.start()

        brace_idx_abs = text.find('{', header_abs_start, schedule_end_abs)
        if brace_idx_abs == -1:
            continue

        try:
            wf_block_body, wf_block_start, wf_block_end = extract_brace_block(text, brace_idx_abs)
        except ValueError:
            continue

        wf_type = extract_key_value(wf_block_body, 'type')
        form_name = extract_key_value(wf_block_body, 'form')
        start_value = extract_key_value(wf_block_body, 'start')
        time_zone = extract_key_value(wf_block_body, 'time zone')

        events: List[Dict[str, Any]] = []
        for ev in EVENT_BLOCK_RE.finditer(wf_block_body):
            event_name = ev.group(1).strip()
            ev_search_from_abs = wf_block_start + ev.end()
            brace_idx_abs_ev = text.find('{', ev_search_from_abs, wf_block_end)
            if brace_idx_abs_ev == -1:
                continue

            try:
                ev_body, _, _ = extract_brace_block(text, brace_idx_abs_ev)
            except ValueError:
                continue

            if event_name.lower() == 'load':
                continue

            actions = parse_actions(ev_body)
            events.append(
                {
                    'event_type': 'on ' + event_name,
                    'actions': actions,
                }
            )

        workflows.append(
            {
                'workflow_name': wf_name,
                'display_name': display_name,
                'type': wf_type,
                'form_name': form_name,
                'start': start_value,
                'time_zone': time_zone.strip('"'),
                'events': events,
                'source_file': os.path.basename(source_file) if source_file else '',
                'start_position': wf_block_start,
                'end_position': wf_block_end,
                'body': wf_block_body,
                'full_source': text[header_abs_start:wf_block_end + 1],
                'start_line': char_to_line(text, header_abs_start),
                'end_line': char_to_line(text, wf_block_end),
            }
        )

    return workflows



def main() -> None:
    parser = argparse.ArgumentParser(description='Eksporter schedule-workflows fra .ds-fil til JSON.')
    parser.add_argument('--file', required=True, help='Sti til .ds-filen')
    parser.add_argument('--out', default='schedule_workflows.json', help='Output JSON (default: schedule_workflows.json)')
    args = parser.parse_args()

    text = read_text(args.file)
    workflows = parse_schedule_workflows(text, source_file=args.file)

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(workflows, f, ensure_ascii=False, indent=2)

    print(f'{len(workflows)} schedule-workflow(s) eksportert til {args.out}')


if __name__ == '__main__':
    main()
