#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ekstraherer alle felter fra Zoho Creator .ds-fil og skriver en FLAT JSON-liste.

Hvert element inneholder:
- form_name
- field_name
- field_type
- definition
- display_name (feltets displayname hvis definert)
- lookup_form (kun for lookup / lookup_list)

Bruk:
  python extract_forms_fields_flat_v2.py input.ds output.json
"""

from __future__ import annotations
import sys
import json
import re
from pathlib import Path

VALUES_SET_RE = re.compile(r'(?mi)^\s*values\s*=\s*\{')
VALUES_ANY_RE = re.compile(r'(?mi)^\s*values\s*=')
LOOKUP_FORM_RE = re.compile(r'(?mi)^\s*values\s*=\s*([A-Za-z0-9_]+)\s*(?:\[.*\])?\s*\.\s*ID\b')
FIELD_DISPLAY_RE = re.compile(r'(?mi)^\s*displayname\s*=\s*(".*?"|\'.*?\')')

def strip_comments_keep_newlines(s: str) -> str:
    out=[]; i=0
    in_str=False; str_char=""
    in_line=False; in_block=False
    while i < len(s):
        ch=s[i]; nxt=s[i+1] if i+1 < len(s) else ""
        if in_line:
            if ch=="\n": in_line=False; out.append("\n")
        elif in_block:
            if ch=="*" and nxt=="/": in_block=False; i+=1
            elif ch=="\n": out.append("\n")
        elif in_str:
            out.append(ch)
            if ch=="\\":
                if i+1 < len(s):
                    out.append(s[i+1]); i+=1
            elif ch==str_char:
                in_str=False; str_char=""
        else:
            if ch=="/" and nxt=="/": in_line=True; i+=1
            elif ch=="/" and nxt=="*": in_block=True; i+=1
            elif ch in ("'", '"'): in_str=True; str_char=ch; out.append(ch)
            else: out.append(ch)
        i+=1
    return "".join(out)

def find_matching_brace(s: str, open_idx: int):
    depth=0; i=open_idx
    in_str=False; str_char=""
    in_line=False; in_block=False
    while i < len(s):
        ch=s[i]; nxt=s[i+1] if i+1 < len(s) else ""
        if in_line:
            if ch=="\n": in_line=False
        elif in_block:
            if ch=="*" and nxt=="/": in_block=False; i+=1
        elif in_str:
            if ch=="\\": i+=1
            elif ch==str_char: in_str=False; str_char=""
        else:
            if ch=="/" and nxt=="/": in_line=True; i+=1
            elif ch=="/" and nxt=="*": in_block=True; i+=1
            elif ch in ("'", '"'): in_str=True; str_char=ch
            elif ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0: return i
        i+=1
    return None

def find_matching_paren(s: str, open_idx: int):
    depth=0; i=open_idx
    in_str=False; str_char=""
    in_line=False; in_block=False
    while i < len(s):
        ch=s[i]; nxt=s[i+1] if i+1 < len(s) else ""
        if in_line:
            if ch=="\n": in_line=False
        elif in_block:
            if ch=="*" and nxt=="/": in_block=False; i+=1
        elif in_str:
            if ch=="\\": i+=1
            elif ch==str_char: in_str=False; str_char=""
        else:
            if ch=="/" and nxt=="/": in_line=True; i+=1
            elif ch=="/" and nxt=="*": in_block=True; i+=1
            elif ch in ("'", '"'): in_str=True; str_char=ch
            elif ch=="(":
                depth+=1
            elif ch==")":
                depth-=1
                if depth==0: return i
        i+=1
    return None

def remove_actions_blocks(form_block: str) -> str:
    out=[]; i=0
    while i < len(form_block):
        m = re.search(r'(?mi)^\s*actions\s*\{', form_block[i:])
        if not m:
            out.append(form_block[i:]); break
        start = i + m.start()
        brace_idx = form_block.find("{", start)
        out.append(form_block[i:start])
        end = find_matching_brace(form_block, brace_idx)
        if end is None: break
        i = end + 1
    return "".join(out)

def classify_field(raw_type: str, definition: str) -> str:
    if not raw_type:
        return "unknown"
    t = raw_type.lower()
    if t == "picklist":
        if VALUES_SET_RE.search(definition):
            return "picklist"
        if VALUES_ANY_RE.search(definition):
            return "lookup"
        return "unknown"
    if t == "list":
        if VALUES_SET_RE.search(definition):
            return "value_list"
        if VALUES_ANY_RE.search(definition):
            return "lookup_list"
        return "unknown"
    return raw_type

def extract_lookup_form(definition: str):
    m = LOOKUP_FORM_RE.search(definition)
    return m.group(1) if m else None

def extract_field_displayname(definition: str):
    m = FIELD_DISPLAY_RE.search(definition)
    if not m: return None
    v = m.group(1)
    return v[1:-1] if len(v)>=2 and v[0]==v[-1] else None

def extract_flat(ds_text: str):
    cleaned = strip_comments_keep_newlines(ds_text)
    flat = []
    for m in re.finditer(r'(?m)^\s*form\s+([A-Za-z0-9_]+)\s*\{', cleaned):
        form_name = m.group(1)
        start = m.start()
        brace_idx = cleaned.find("{", m.end()-1)
        end = find_matching_brace(cleaned, brace_idx)
        if end is None:
            continue

        block = cleaned[start:end+1]
        block_wo_actions = remove_actions_blocks(block)

        i=0
        while i < len(block_wo_actions):
            nl = block_wo_actions.find("\n", i)
            if nl == -1: break
            line = block_wo_actions[i:nl]; i = nl + 1
            if not line.strip(): continue
            if "=" in line: continue

            field_name = line.strip()
            j=i
            while j < len(block_wo_actions) and block_wo_actions[j].isspace(): j+=1

            if j < len(block_wo_actions) and block_wo_actions[j]=="(":
                endp = find_matching_paren(block_wo_actions, j)
                if endp is None: continue
                definition = block_wo_actions[j:endp+1].rstrip()

                mt = re.search(r'(?mi)^\s*type\s*=\s*([A-Za-z0-9_]+)', definition)
                raw_type = mt.group(1) if mt else None
                if raw_type and raw_type.lower() in {"section","submit","reset"}:
                    i=endp+1; continue

                field_type = classify_field(raw_type, definition)

                obj = {
                    "form_name": form_name,
                    "field_name": field_name,
                    "field_type": field_type,
                    "definition": definition
                }

                fdn = extract_field_displayname(definition)
                if fdn:
                    obj["display_name"] = fdn

                if field_type in {"lookup","lookup_list"}:
                    lf = extract_lookup_form(definition)
                    if lf:
                        obj["lookup_form"] = lf

                flat.append(obj)
                i=endp+1

    return flat

def main() -> int:
    if len(sys.argv) != 3:
        print("Bruk: python extract_forms_fields_flat_v2.py input.ds output.json", file=sys.stderr)
        return 2

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    ds_text = in_path.read_text(encoding="utf-8", errors="replace")
    data = extract_flat(ds_text)

    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Skrev {len(data)} felter til: {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
