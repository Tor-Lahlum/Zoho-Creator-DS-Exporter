#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_full_export.py
-----------------
Single entry-point script that reads a Zoho Creator .ds export file and
produces a set of JSON files with structure and code for:

- Global functions (Deluge)
- Form workflows (with Deluge)
- Report workflows (custom actions)
- Forms (deduplicated)
- Form fields
- Reports
- Report fields
- Pages
- Page components (with ZML snippets)
"""

import re
import json
import argparse
import os
from typing import List, Dict, Any, Tuple


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def read_text(path: str) -> str:
    """Read text file as UTF-8."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def char_to_line(text: str, idx: int) -> int:
    """Convert character index to 1-based line number."""
    return text.count("\n", 0, idx) + 1


def extract_brace_block(text: str, open_idx: int) -> Tuple[str, int, int]:
    """
    Given index of '{' in `text`, return (body, body_start_idx, body_end_idx),
    where body is substring between '{' and matching '}'.
    body_start_idx / body_end_idx are indices in the original text:
      [body_start_idx, body_end_idx) is the body.
    """
    if text[open_idx] != "{":
        open_idx = text.find("{", open_idx)
        if open_idx == -1:
            raise ValueError("extract_brace_block: '{' not found")
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i], open_idx + 1, i
    raise ValueError(f"Unbalanced braces from position {open_idx}")


def extract_paren_block(text: str, open_idx: int) -> Tuple[str, int, int]:
    """
    Given index of '(' in `text`, return (body, body_start_idx, body_end_idx),
    with indices in the original text.
    """
    if text[open_idx] != "(":
        open_idx = text.find("(", open_idx)
        if open_idx == -1:
            raise ValueError("extract_paren_block: '(' not found")
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i], open_idx + 1, i
    raise ValueError(f"Unbalanced parentheses from position {open_idx}")


# ---------------------------------------------------------------------------
# Functions (Deluge)
# ---------------------------------------------------------------------------

FUNC_HEADER_RE = re.compile(
    r'(?m)^\s*(void|string|map|list|int|bool)\s+((?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*)\s*\('
)


def _split_name(full: str) -> Tuple[Any, str]:
    if "." in full:
        ns, name = full.rsplit(".", 1)
        return ns, name
    return None, full


def list_functions_with_code(text: str, source_file: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for m in FUNC_HEADER_RE.finditer(text):
        return_type = m.group(1)
        full = m.group(2)
        ns, name = _split_name(full)

        header_idx = m.start()
        header_line = char_to_line(text, header_idx)

        brace_idx = text.find("{", m.end())
        if brace_idx == -1:
            continue

        try:
            body, body_start, body_end = extract_brace_block(text, brace_idx)
        except ValueError:
            continue

        full_source = text[header_idx : body_end + 1]

        out.append(
            {
                "position": header_idx,
                "namespace": ns,
                "name": name,
                "full_name": full,
                "return_type": return_type,
                "header_line": header_line,
                "body_start": body_start,
                "body_end": body_end,
                "body": body,
                "full_source": full_source,
                "source_file": os.path.basename(source_file),
            }
        )

    return out


# ---------------------------------------------------------------------------
# Form workflows (workflow { form { ... } })
# ---------------------------------------------------------------------------

WF_HEADER_RE = re.compile(
    r'^\s*(?P<name>\w+)\s+as\s+"(?P<display>[^"]+)"\s*$',
    re.MULTILINE,
)

WF_EVENT_HEADER_RE = re.compile(r"^\s*on\s+(.+?)\s*$", re.MULTILINE)


def _find_workflow_form_section(text: str) -> Tuple[str, int, int]:
    """
    Find the workflow { ... form { ... } ... } section and return the inner
    form { ... } body with absolute indices.
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

    raise ValueError("No workflow form-section found")


def parse_form_workflows_with_code(text: str, source_file: str) -> List[Dict[str, Any]]:
    try:
        form_body, form_start_abs, form_end_abs = _find_workflow_form_section(text)
    except ValueError:
        return []

    workflows: List[Dict[str, Any]] = []

    for m in WF_HEADER_RE.finditer(form_body):
        wf_name = m.group("name")
        display_name = m.group("display")
        header_rel_start = m.start()
        header_abs_start = form_start_abs + header_rel_start

        brace_idx_abs = text.find("{", header_abs_start, form_end_abs)
        if brace_idx_abs == -1:
            continue

        wf_block_body, wf_block_start, wf_block_end = extract_brace_block(text, brace_idx_abs)

        type_match = re.search(r"\btype\s*=\s*([^\n]+)", wf_block_body)
        form_match = re.search(r"\bform\s*=\s*([^\n]+)", wf_block_body)
        event_match = re.search(r"\brecord event\s*=\s*([^\n]+)", wf_block_body)

        wf_type = type_match.group(1).strip() if type_match else ""
        form_name = form_match.group(1).strip() if form_match else ""
        record_event = event_match.group(1).strip() if event_match else ""

        events: List[Dict[str, Any]] = []
        for ev in WF_EVENT_HEADER_RE.finditer(wf_block_body):
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

            ev_body, ev_body_start, ev_body_end = extract_brace_block(text, brace_idx_abs_ev)

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
                "source_file": os.path.basename(source_file),
                "start_line": char_to_line(text, header_abs_start),
                "end_line": char_to_line(text, wf_block_end),
            }
        )

    return workflows


# ---------------------------------------------------------------------------
# Reports section helpers
# ---------------------------------------------------------------------------

def _find_reports_sections(text: str) -> List[Tuple[str, int, int]]:
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


# ---------------------------------------------------------------------------
# Report workflows (custom actions)
# ---------------------------------------------------------------------------

def parse_report_workflows_with_code(text: str, source_file: str) -> List[Dict[str, Any]]:
    reports: List[Dict[str, Any]] = []

    for body, body_start, body_end in _find_reports_sections(text):
        for m in REPORT_HEADER_RE.finditer(body):
            report_type = m.group(1).strip()
            report_name = m.group(2)
            header_abs_start = body_start + m.start()

            brace_idx_abs = text.find("{", header_abs_start, body_end)
            if brace_idx_abs == -1:
                continue

            report_body, report_start, report_end = extract_brace_block(text, brace_idx_abs)

            m_disp = re.search(r'(?i)\bdisplayname\s*=\s*"([^"]*)"', report_body)
            display_name = m_disp.group(1) if m_disp else ""

            actions: List[Dict[str, Any]] = []

            # Block-style: custom actions ( ... )
            pos = 0
            marker = "custom actions"
            while True:
                idx = report_body.find(marker, pos)
                if idx == -1:
                    break

                open_paren_rel = report_body.find("(", idx)
                if open_paren_rel == -1:
                    break

                custom_body, custom_start_rel, custom_end_rel = extract_paren_block(
                    report_body, open_paren_rel
                )
                custom_abs_base = report_start + custom_start_rel

                for mm in re.finditer(r'^\s*"(?P<label>[^"]+)"\s*\(', custom_body, re.MULTILINE):
                    label = mm.group("label")
                    open_paren_for_label = custom_body.find("(", mm.end() - 1)
                    if open_paren_for_label == -1:
                        continue

                    conf_body, conf_start_rel, conf_end_rel = extract_paren_block(
                        custom_body, open_paren_for_label
                    )

                    action_abs_start = custom_abs_base + mm.start()
                    action_abs_end = custom_abs_base + conf_end_rel

                    m_wf = re.search(r"\bworkflow\s*=\s*([A-Za-z0-9_]+)", conf_body)
                    workflow_name = m_wf.group(1) if m_wf else ""

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

            # Inline style: custom action "Label" ( ... )
            INLINE_RE = re.compile(
                r'\bcustom action\s+"(?P<label>[^"]+)"\s*\(', re.MULTILINE
            )

            for mm in INLINE_RE.finditer(report_body):
                label = mm.group("label")
                open_paren_rel = report_body.find("(", mm.end() - 1)
                if open_paren_rel == -1:
                    continue

                conf_body, conf_start_rel, conf_end_rel = extract_paren_block(
                    report_body, open_paren_rel
                )

                action_abs_start = report_start + mm.start()
                action_abs_end = report_start + conf_end_rel

                m_wf = re.search(r"\bworkflow\s*=\s*([A-Za-z0-9_]+)", conf_body)
                workflow_name = m_wf.group(1) if m_wf else ""

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
                        "source_file": os.path.basename(source_file),
                        "start_line": char_to_line(text, header_abs_start),
                        "end_line": char_to_line(text, report_end),
                    }
                )

    return reports


# ---------------------------------------------------------------------------
# Reports (structure)
# ---------------------------------------------------------------------------

def parse_reports(text: str, source_file: str) -> List[Dict[str, Any]]:
    reports: List[Dict[str, Any]] = []

    for body, body_start, body_end in _find_reports_sections(text):
        for m in REPORT_HEADER_RE.finditer(body):
            report_type = m.group(1).strip()
            report_name = m.group(2)
            header_abs_start = body_start + m.start()

            brace_idx_abs = text.find("{", header_abs_start, body_end)
            if brace_idx_abs == -1:
                continue

            report_body, report_start, report_end = extract_brace_block(text, brace_idx_abs)

            m_disp = re.search(r'(?i)\bdisplayname\s*=\s*"([^"]*)"', report_body)
            display_name = m_disp.group(1) if m_disp else ""

            base_form = None
            m_form = re.search(r"show\s+all\s+rows\s+from\s+([A-Za-z0-9_]+)", report_body)
            if not m_form:
                m_form = re.search(r"show\s+rows\s+from\s+([A-Za-z0-9_]+)", report_body)
            if m_form:
                base_form = m_form.group(1)

            m_tmpl = re.search(r"\btemplate\s*=\s*([A-Za-z0-9_]+)", report_body)
            template = m_tmpl.group(1) if m_tmpl else None

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
                    "source_file": os.path.basename(source_file),
                    "start_line": char_to_line(text, header_abs_start),
                    "end_line": char_to_line(text, report_end),
                    "start_position": report_start,
                    "end_position": report_end,
                }
            )

    return reports


# ---------------------------------------------------------------------------
# Report fields
# ---------------------------------------------------------------------------

REPORT_FIELD_RE = re.compile(
    r'^([A-Za-z0-9_.]+)(?:\s+as\s+"([^"]*)")?$'
)


def _parse_fields_from_rows_block(
    text: str,
    rows_body: str,
    rows_start_abs: int,
    report_name: str,
    source_file: str,
) -> List[Dict[str, Any]]:
    fields: List[Dict[str, Any]] = []

    lines = rows_body.splitlines(keepends=True)
    cursor = 0
    idx = 0
    order = 0

    while idx < len(lines):
        line = lines[idx]
        line_stripped = line.strip()

        line_abs_start = rows_start_abs + cursor
        cursor += len(line)

        if not line_stripped or line_stripped in ("(", ")"):
            idx += 1
            continue

        m_field = REPORT_FIELD_RE.match(line_stripped)
        if not m_field:
            idx += 1
            continue

        expr = m_field.group(1)
        display_name = m_field.group(2) if m_field.group(2) is not None else None

        config = None
        j = idx + 1

        while j < len(lines) and lines[j].strip() == "":
            cursor += len(lines[j])
            j += 1

        if j < len(lines) and lines[j].lstrip().startswith("("):
            depth = 0
            config_lines: List[str] = []
            k = j
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
                "source_file": os.path.basename(source_file),
                "start_line": char_to_line(text, line_abs_start),
            }
        )

    return fields


def parse_report_fields(text: str, source_file: str) -> List[Dict[str, Any]]:
    all_fields: List[Dict[str, Any]] = []

    for body, body_start, body_end in _find_reports_sections(text):
        for m in REPORT_HEADER_RE.finditer(body):
            report_name = m.group(2)
            header_abs_start = body_start + m.start()

            brace_idx_abs = text.find("{", header_abs_start, body_end)
            if brace_idx_abs == -1:
                continue

            report_body, report_start, report_end = extract_brace_block(text, brace_idx_abs)

            m_rows = re.search(
                r"show\s+all\s+rows\s+from\s+([A-Za-z0-9_]+)|show\s+rows\s+from\s+([A-Za-z0-9_]+)",
                report_body,
            )
            if not m_rows:
                continue

            rel_idx = m_rows.end()
            open_paren_rel = report_body.find("(", rel_idx)
            if open_paren_rel == -1:
                continue

            open_paren_abs = report_start + open_paren_rel
            rows_body, rows_start_abs, rows_end_abs = extract_paren_block(text, open_paren_abs)

            fields = _parse_fields_from_rows_block(
                text=text,
                rows_body=rows_body,
                rows_start_abs=rows_start_abs,
                report_name=report_name,
                source_file=source_file,
            )
            all_fields.extend(fields)

    return all_fields


# ---------------------------------------------------------------------------
# Forms (structure, deduplicated)
# ---------------------------------------------------------------------------

def _find_forms_sections(text: str) -> List[Tuple[str, int, int]]:
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

FORM_FIELD_HEADER_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", re.MULTILINE)


def parse_forms(text: str, source_file: str) -> List[Dict[str, Any]]:
    """
    Parse all form definitions, deduplicate by form_name.
    If a form appears in multiple forms { } blocks, keep the one with the
    largest body (full definition vs. small overrides).
    """
    forms_by_name: Dict[str, Dict[str, Any]] = {}

    for body, body_start, body_end in _find_forms_sections(text):
        for m in FORM_HEADER_RE.finditer(body):
            form_name = m.group(1)
            header_abs_start = body_start + m.start()

            brace_idx_abs = text.find("{", header_abs_start, body_end)
            if brace_idx_abs == -1:
                continue

            form_body, form_start, form_end = extract_brace_block(text, brace_idx_abs)

            m_disp = re.search(r'(?i)\bdisplayname\s*=\s*"([^"]*)"', form_body)
            display_name = m_disp.group(1) if m_disp else ""

            m_desc = re.search(r'(?i)\bdescription\s*=\s*"([^"]*)"', form_body)
            description = m_desc.group(1) if m_desc else ""

            m_success = re.search(r'(?i)\bsuccess message\s*=\s*"([^"]*)"', form_body)
            success_message = m_success.group(1) if m_success else ""

            rec = {
                "form_name": form_name,
                "display_name": display_name,
                "description": description,
                "success_message": success_message,
                "source_file": os.path.basename(source_file),
                "start_line": char_to_line(text, header_abs_start),
                "end_line": char_to_line(text, form_end),
                "start_position": form_start,
                "end_position": form_end,
                "body": form_body,
            }

            prev = forms_by_name.get(form_name)
            if prev is None or len(rec["body"]) > len(prev["body"]):
                forms_by_name[form_name] = rec

    return list(forms_by_name.values())


# ---------------------------------------------------------------------------
# Form fields (using first forms section where full definitions live)
# ---------------------------------------------------------------------------

def _find_first_forms_section(text: str) -> Tuple[str, int, int]:
    m = re.search(r"^\s*forms\s*$", text, re.MULTILINE)
    if not m:
        raise ValueError("No 'forms' section found in .ds file")
    brace_idx = text.find("{", m.end())
    if brace_idx == -1:
        raise ValueError("No '{' after 'forms'")
    body, start, end = extract_brace_block(text, brace_idx)
    return body, start, end


def _extract_paren_block_local(s: str, open_idx: int) -> Tuple[str, int, int]:
    if s[open_idx] != "(":
        open_idx = s.find("(", open_idx)
        if open_idx == -1:
            raise ValueError("No '(' at expected position")
    depth = 0
    for i in range(open_idx, len(s)):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return s[open_idx + 1 : i], open_idx + 1, i
    raise ValueError("Unbalanced parentheses (local)")


def parse_form_fields(text: str, source_file: str) -> List[Dict[str, Any]]:
    """
    Parse all form fields from the FIRST forms { } block (where full form
    definitions live) and return a flat list.
    """
    all_fields: List[Dict[str, Any]] = []

    try:
        forms_body, forms_start, forms_end = _find_first_forms_section(text)
    except ValueError:
        return []

    for m_form in FORM_HEADER_RE.finditer(forms_body):
        form_name = m_form.group(1)
        form_header_abs = forms_start + m_form.start()

        brace_idx_abs = text.find("{", form_header_abs, forms_end)
        if brace_idx_abs == -1:
            continue

        form_body, form_start, form_end = extract_brace_block(text, brace_idx_abs)

        order = 0

        for m_field in FORM_FIELD_HEADER_RE.finditer(form_body):
            field_name = m_field.group(1)
            header_local_idx = m_field.start()
            header_abs_idx = form_start + header_local_idx

            search_from = m_field.end()
            open_paren_local = form_body.find("(", search_from)
            if open_paren_local == -1:
                # No config-block – skip (could be on load, etc.)
                continue

            try:
                config_body, c_start_local, c_end_local = _extract_paren_block_local(
                    form_body, open_paren_local
                )
            except ValueError:
                continue

            order += 1
            config = config_body.strip()

            display_name = None
            ftype = None
            required = False
            default_value = None
            lookup_details: Dict[str, str] = {}

            m_disp = re.search(r'displayname\s*=\s*"([^"]*)"', config, re.IGNORECASE)
            if m_disp:
                display_name = m_disp.group(1)

            m_type = re.search(r'\btype\s*=\s*([A-Za-z0-9_]+)', config)
            if m_type:
                ftype = m_type.group(1)

            if re.search(r'\brequired\s*=\s*true', config, re.IGNORECASE):
                required = True

            m_def = re.search(r'\bdefault\s*=\s*"([^"]*)"', config, re.IGNORECASE)
            if m_def:
                default_value = m_def.group(1)

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
                    "source_file": os.path.basename(source_file),
                    "start_line": char_to_line(text, header_abs_idx),
                }
            )

    return all_fields


# ---------------------------------------------------------------------------
# Pages (structure)
# ---------------------------------------------------------------------------

def _find_pages_section(text: str) -> Tuple[str, int, int]:
    m = re.search(r"^\s*pages\s*$", text, re.MULTILINE)
    if not m:
        raise ValueError("No 'pages' section found in .ds file")
    brace_idx = text.find("{", m.end())
    if brace_idx == -1:
        raise ValueError("No '{' after 'pages'")
    body, start, end = extract_brace_block(text, brace_idx)
    return body, start, end


PAGE_HEADER_RE = re.compile(r"^\s*page\s+(\w+)", re.MULTILINE)


def parse_pages(text: str, source_file: str) -> List[Dict[str, Any]]:
    try:
        pages_body, pages_start_abs, pages_end_abs = _find_pages_section(text)
    except ValueError:
        return []

    pages: List[Dict[str, Any]] = []

    for m in PAGE_HEADER_RE.finditer(pages_body):
        page_name = m.group(1)
        header_rel_start = m.start()
        header_abs_start = pages_start_abs + header_rel_start

        brace_idx_abs = text.find("{", header_abs_start, pages_end_abs)
        if brace_idx_abs == -1:
            continue

        page_body, page_start, page_end = extract_brace_block(text, brace_idx_abs)

        m_disp = re.search(r'(?i)\bdisplayname\s*=\s*"([^"]*)"', page_body)
        display_name = m_disp.group(1) if m_disp else ""

        content_match = re.search(r'Content="', page_body)
        if content_match:
            content_start = content_match.end()
            content_end = page_body.find('"', content_start)
            if content_end == -1:
                content_end = len(page_body)
            content_str = page_body[content_start:content_end]
            has_content = True
            content_length = len(content_str)
        else:
            has_content = False
            content_length = 0

        pages.append(
            {
                "page_name": page_name,
                "display_name": display_name,
                "has_content": has_content,
                "content_length": content_length,
                "source_file": os.path.basename(source_file),
                "start_line": char_to_line(text, header_abs_start),
                "end_line": char_to_line(text, page_end),
                "start_position": page_start,
                "end_position": page_end,
            }
        )

    return pages


# ---------------------------------------------------------------------------
# Page components (with ZML snippet)
# ---------------------------------------------------------------------------

def _parse_components_from_content(content: str) -> List[Dict[str, Any]]:
    """
    Parse components from ZML content in a Page Content="..." block.
    """
    interesting_tags = {"report", "form", "button", "chart", "image", "text"}
    components: List[Dict[str, Any]] = []

    TAG_RE = re.compile(r"<([A-Za-z]+)\b([^>]*)>")

    comp_id = 0
    for m in TAG_RE.finditer(content):
        tag = m.group(1)
        attrs_raw = m.group(2) or ""

        if tag not in interesting_tags:
            continue

        comp_id += 1

        zml_snippet = m.group(0).strip()

        attrs: Dict[str, str] = {}
        for ma in re.finditer(r"([A-Za-z_]+)\s*=\s*'([^']*)'", attrs_raw):
            key = ma.group(1)
            val = ma.group(2)
            attrs[key] = val

        title = None
        for key in ["title", "displayName", "displayname", "text", "label", "name"]:
            if key in attrs:
                title = attrs[key]
                break

        target_type = None
        target_name = None
        key_type_map = [
            ("formLinkName", "form"),
            ("formName", "form"),
            ("viewLinkName", "report"),
            ("reportLinkName", "report"),
            ("viewName", "report"),
            ("reportName", "report"),
            ("componentLinkName", "component"),
            ("linkName", "component"),
        ]
        for k, t in key_type_map:
            if k in attrs:
                target_type = t
                target_name = attrs[k]
                break

        components.append(
            {
                "component_id": comp_id,
                "component_type": tag,
                "title": title,
                "target_type": target_type,
                "target_name": target_name,
                "layout_region": None,
                "order": comp_id,
                "zml": zml_snippet,
            }
        )

    return components


def parse_page_components(text: str, source_file: str) -> List[Dict[str, Any]]:
    try:
        pages_body, pages_start_abs, pages_end_abs = _find_pages_section(text)
    except ValueError:
        return []

    all_components: List[Dict[str, Any]] = []

    for m in PAGE_HEADER_RE.finditer(pages_body):
        page_name = m.group(1)
        header_rel_start = m.start()
        header_abs_start = pages_start_abs + header_rel_start

        brace_idx_abs = text.find("{", header_abs_start, pages_end_abs)
        if brace_idx_abs == -1:
            continue

        page_body, page_start, page_end = extract_brace_block(text, brace_idx_abs)

        content_match = re.search(r'Content="', page_body)
        if not content_match:
            continue

        content_start = content_match.end()
        content_end = page_body.find('"', content_start)
        if content_end == -1:
            content_end = len(page_body)
        content_str = page_body[content_start:content_end]

        components = _parse_components_from_content(content_str)
        for comp in components:
            rec = dict(comp)
            rec["page_name"] = page_name
            rec["source_file"] = os.path.basename(source_file)
            all_components.append(rec)

    return all_components


# ---------------------------------------------------------------------------
# IO helpers and main orchestration
# ---------------------------------------------------------------------------

def ensure_outdir(path: str) -> str:
    if not path:
        return "."
    os.makedirs(path, exist_ok=True)
    return path


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Full export of Zoho .ds file to multiple JSON files (forms, reports, workflows, pages, functions)."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to .ds file",
    )
    parser.add_argument(
        "--outdir",
        default=".",
        help="Output directory (default: .)",
    )
    args = parser.parse_args()

    outdir = ensure_outdir(args.outdir)
    text = read_text(args.file)

    # Functions
    funcs = list_functions_with_code(text, source_file=args.file)
    write_json(os.path.join(outdir, "functions_with_code.json"), funcs)

    # Form workflows
    form_wf = parse_form_workflows_with_code(text, source_file=args.file)
    write_json(os.path.join(outdir, "form_workflows_with_code.json"), form_wf)

    # Report workflows
    report_wf = parse_report_workflows_with_code(text, source_file=args.file)
    write_json(os.path.join(outdir, "report_workflows_with_code.json"), report_wf)

    # Reports
    reports = parse_reports(text, source_file=args.file)
    write_json(os.path.join(outdir, "reports.json"), reports)

    # Report fields
    report_fields = parse_report_fields(text, source_file=args.file)
    write_json(os.path.join(outdir, "report_fields.json"), report_fields)

    # Forms
    forms = parse_forms(text, source_file=args.file)
    write_json(os.path.join(outdir, "forms.json"), forms)

    # Form fields
    form_fields = parse_form_fields(text, source_file=args.file)
    write_json(os.path.join(outdir, "form_fields.json"), form_fields)

    # Pages
    pages = parse_pages(text, source_file=args.file)
    write_json(os.path.join(outdir, "pages.json"), pages)

    # Page components
    page_components = parse_page_components(text, source_file=args.file)
    write_json(os.path.join(outdir, "page_components.json"), page_components)

    print("Export complete:")
    print(f"  Functions:        {len(funcs)}")
    print(f"  Form workflows:   {len(form_wf)}")
    print(f"  Report workflows: {len(report_wf)}")
    print(f"  Reports:          {len(reports)}")
    print(f"  Report fields:    {len(report_fields)}")
    print(f"  Forms:            {len(forms)}")
    print(f"  Form fields:      {len(form_fields)}")
    print(f"  Pages:            {len(pages)}")
    print(f"  Page components:  {len(page_components)}")
    print(f"Output directory:   {outdir}")


if __name__ == "__main__":
    main()
