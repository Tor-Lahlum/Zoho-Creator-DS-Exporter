#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_page_components_export.py
----------------------------
Ekstraherer ALLE komponenter fra alle pages i en Zoho .ds-fil og eksporterer dem
som en flat liste i JSON.

Vi ser kun på "faglige" komponenter i ZML-en:
- <report ...>
- <form ...>
- <button ...>
- <chart ...>
- <image ...>
- <text ...>

I denne versjonen tar vi også med selve ZML-snippet for hver komponent.

Per komponent får du:
- page_name
- component_id    : løpenummer innen siden
- component_type  : f.eks. report, form, button, chart, image, text
- title           : displayName/text/label hvis funnet
- target_type     : form | report | component | None (utledet fra *LinkName-attributter)
- target_name     : navnet på form/report/komponent hvis funnet
- layout_region   : None (placeholder for senere utvidelse)
- order           : samme som component_id
- zml             : selve tag-snippet slik det står i Content-strengen
- source_file
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


def extract_brace_block(text: str, open_idx: int) -> Tuple[str, int, int]:
    """
    Gitt indeks til en '{' i `text`, returner innholdet inni blokken,
    samt start- og sluttindeks (eksklusiv slutt).
    """
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


def find_pages_section(text: str) -> Tuple[str, int, int]:
    """
    Finn `pages { ... }`-seksjonen og returner (body, start_abs, end_abs).
    """
    m = re.search(r"^\s*pages\s*$", text, re.MULTILINE)
    if not m:
        raise ValueError("Fant ingen 'pages'-seksjon i .ds-filen")
    brace_idx = text.find("{", m.end())
    if brace_idx == -1:
        raise ValueError("Fant ikke '{' etter 'pages'")
    body, start, end = extract_brace_block(text, brace_idx)
    return body, start, end


PAGE_HEADER_RE = re.compile(r"^\s*page\s+(\w+)", re.MULTILINE)


def parse_components_from_content(content: str) -> list:
    """
    Parse komponenter fra ZML Content-streng.

    Vi ser etter:
      - report, form, button, chart, image, text
    """
    interesting_tags = {"report", "form", "button", "chart", "image", "text"}

    components = []

    # Regex: <tagName ...>
    TAG_RE = re.compile(r"<([A-Za-z]+)\b([^>]*)>")

    comp_id = 0
    for m in TAG_RE.finditer(content):
        tag = m.group(1)
        attrs_raw = m.group(2) or ""

        if tag not in interesting_tags:
            continue

        comp_id += 1

        # Hele ZML-taggen som den står i Content
        zml_snippet = m.group(0).strip()

        # Parse attributter: key = 'value'
        attrs: Dict[str, str] = {}
        for ma in re.finditer(r"([A-Za-z_]+)\s*=\s*'([^']*)'", attrs_raw):
            key = ma.group(1)
            val = ma.group(2)
            attrs[key] = val

        # Tittel/label
        title = None
        for key in ["title", "displayName", "displayname", "text", "label", "name"]:
            if key in attrs:
                title = attrs[key]
                break

        # Target-type og -navn
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


def parse_page_components(text: str, source_file: str = "") -> list:
    """
    Parse alle pages og returner en flat liste med komponenter fra alle pages.
    """
    pages_body, pages_start_abs, pages_end_abs = find_pages_section(text)
    all_components = []

    for m in PAGE_HEADER_RE.finditer(pages_body):
        page_name = m.group(1)
        header_rel_start = m.start()
        header_abs_start = pages_start_abs + header_rel_start

        # Finn '{' som starter selve page-blokken
        brace_idx_abs = text.find("{", header_abs_start, pages_end_abs)
        if brace_idx_abs == -1:
            continue

        page_body, page_start, page_end = extract_brace_block(text, brace_idx_abs)

        # Content
        content_match = re.search(r'Content="', page_body)
        if not content_match:
            continue

        content_start = content_match.end()
        content_end = page_body.find('"', content_start)
        if content_end == -1:
            content_end = len(page_body)
        content_str = page_body[content_start:content_end]

        components = parse_components_from_content(content_str)
        for comp in components:
            comp_rec = dict(comp)  # kopi
            comp_rec["page_name"] = page_name
            comp_rec["source_file"] = os.path.basename(source_file) if source_file else ""
            all_components.append(comp_rec)

    return all_components


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksporter page-komponenter fra .ds-fil til JSON (flat liste)."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Sti til .ds-filen",
    )
    parser.add_argument(
        "--out",
        default="page_components.json",
        help="Filnavn for resultat (default: page_components.json)",
    )
    args = parser.parse_args()

    text = read_text(args.file)
    components = parse_page_components(text, source_file=args.file)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(components, f, ensure_ascii=False, indent=2)

    print(f"{len(components)} komponent(er) eksportert til {args.out}")


if __name__ == "__main__":
    main()
