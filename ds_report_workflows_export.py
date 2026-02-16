#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional, Set


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def char_to_line(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def extract_brace_block(text: str, open_idx: int) -> Tuple[str, int, int]:
    if text[open_idx] != "{":
        raise ValueError(f"Expected '{{' at {open_idx}")
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i], open_idx + 1, i
    raise ValueError(f"Unbalanced braces starting at {open_idx}")


WF_HEADER_RE = re.compile(r'^\s*(?P<name>\w+)\s+as\s+"(?P<label>[^"]+)"\s*$', re.MULTILINE)


def load_referenced_workflows(actions_json_path: Optional[str]) -> Optional[Set[str]]:
    if not actions_json_path:
        return None
    data = json.loads(Path(actions_json_path).read_text(encoding="utf-8"))
    names: Set[str] = set()
    for report in data:
        for action in report.get("actions", []):
            wf = (action.get("workflow_name") or "").strip()
            if wf:
                names.add(wf)
    return names


def export_workflow_definitions(ds_text: str, referenced_only: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    workflows: List[Dict[str, Any]] = []

    for m in WF_HEADER_RE.finditer(ds_text):
        wf_name = m.group("name")
        wf_label = m.group("label")

        if referenced_only is not None and wf_name not in referenced_only:
            continue

        brace_idx = ds_text.find("{", m.end())
        if brace_idx == -1:
            continue

        try:
            body, body_start, body_end = extract_brace_block(ds_text, brace_idx)
        except ValueError:
            continue

        # Kun workflows definert som functions (type = functions)
        if not re.search(r'(?im)^\s*type\s*=\s*functions\s*$', body):
            continue

        block_start = m.start()
        block_end = body_end  # pos til '}' i ds_text

        workflows.append(
            {
                "workflow_name": wf_name,
                "display_name": wf_label,
                "start_line": char_to_line(ds_text, block_start),
                "end_line": char_to_line(ds_text, block_end),
                "body": body,
                "full_source": ds_text[block_start : block_end + 1],
            }
        )

    return workflows


def main() -> None:
    ap = argparse.ArgumentParser(description="Eksporter workflow-definisjoner (type=functions) fra Zoho .ds til JSON.")
    ap.add_argument("--ds", required=True, help="Sti til .ds-filen")
    ap.add_argument("--out", default="workflow_definitions.json", help="Output JSON (default: workflow_definitions.json)")
    ap.add_argument(
        "--actions-json",
        default="",
        help="(Valgfritt) JSON fra script A for å eksportere kun refererte workflows",
    )
    args = ap.parse_args()

    ds_text = read_text(args.ds)
    referenced = load_referenced_workflows(args.actions_json) if args.actions_json else None
    workflows = export_workflow_definitions(ds_text, referenced_only=referenced)

    Path(args.out).write_text(json.dumps(workflows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(workflows)} workflow(s) eksportert til {args.out}")


if __name__ == "__main__":
    main()
