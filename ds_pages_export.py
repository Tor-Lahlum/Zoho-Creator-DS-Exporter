#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_pages_export.py
------------------
Eksporterer alle pages fra en Zoho .ds-fil til én JSON-fil med kun page-metadata
(ingen komponenter).

Per page:
- page_name
- display_name
- has_content
- content_length
- source_file
- start_line
- end_line
- start_position
- end_position

Scriptet er robust mot .ds-filer som ikke har pages-seksjon.
Da skrives en tom JSON-liste, og det rapporteres 0 pages eksportert.
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
        open_idx = text.find("{", open_idx)
        if open_idx == -1:
            raise ValueError("Fant ikke '{' ved forventet posisjon")
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


def find_pages_section(text: str) -> Optional[Tuple[str, int, int]]:
    m = re.search(r"^\s*pages\s*$", text, re.MULTILINE)
    if not m:
        return None

    brace_idx = text.find("{", m.end())
    if brace_idx == -1:
        return None

    try:
        body, start, end = extract_brace_block(text, brace_idx)
    except ValueError:
        return None

    return body, start, end


PAGE_HEADER_RE = re.compile(r"^\s*page\s+(\w+)", re.MULTILINE)


def parse_pages(text: str, source_file: str = "") -> List[Dict[str, Any]]:
    section = find_pages_section(text)
    if section is None:
        return []

    pages_body, pages_start_abs, pages_end_abs = section
    pages: List[Dict[str, Any]] = []

    for m in PAGE_HEADER_RE.finditer(pages_body):
        page_name = m.group(1)
        header_rel_start = m.start()
        header_abs_start = pages_start_abs + header_rel_start

        brace_idx_abs = text.find("{", header_abs_start, pages_end_abs)
        if brace_idx_abs == -1:
            continue

        try:
            page_body, page_start, page_end = extract_brace_block(text, brace_idx_abs)
        except ValueError:
            continue

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
                "source_file": os.path.basename(source_file) if source_file else "",
                "start_line": char_to_line(text, header_abs_start),
                "end_line": char_to_line(text, page_end),
                "start_position": page_start,
                "end_position": page_end,
            }
        )

    return pages


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksporter pages fra .ds-fil til JSON (kun page-metadata)."
    )
    parser.add_argument("--file", required=True, help="Sti til .ds-filen")
    parser.add_argument("--out", default="pages.json", help="Filnavn for resultat (default: pages.json)")
    args = parser.parse_args()

    text = read_text(args.file)
    pages = parse_pages(text, source_file=args.file)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)

    print(f"{len(pages)} page(s) eksportert til {args.out}")


if __name__ == "__main__":
    main()
