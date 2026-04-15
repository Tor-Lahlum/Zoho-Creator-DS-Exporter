#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ds_functions_with_code_export.py
--------------------------------
Ekstraherer alle Deluge-funksjoner i en Zoho .ds-fil og eksporterer resultatet som JSON.

For hver funksjon får du:
- position          : tegnindeks (0-basert) til starten av funksjonsheadere
- namespace         : ev. namespace (delen før siste punktum), ellers None
- name              : selve funksjonsnavnet
- full_name         : namespace + navn, hvis namespace finnes
- return_type       : void|string|map|list|int|bool
- header_line       : linjenummer der funksjonen starter
- body_start        : tegnindeks til første tegn etter '{'
- body_end          : tegnindeks til tilhørende '}' (slutt på funksjonsblokken)
- body              : selve Deluge-koden INNE i funksjonen (uten ytre klammer)
- full_source       : hele funksjonen slik den står i .ds-filen (header + kropp)

JSON-strukturen kan senere importeres i Zoho Creator, og Deluge-koden kan legges
i multiline-strengfelt.
"""

import re
import json
import argparse
from typing import List, Tuple, Optional, Dict, Any


# Gruppe 1 = returtype, gruppe 2 = fullt navn (ev. namespace + navn)
HEADER_RE = re.compile(
    r'(?m)^\s*(void|string|map|list|int|bool)\s+((?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*)\s*\('
)


def read_text(path: str) -> str:
    """Les inn en tekstfil som UTF-8 (ignorerer feil)."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def split_name(full: str) -> Tuple[Optional[str], str]:
    """Splitt ev. namespace.fullname i (namespace, name)."""
    if "." in full:
        ns, name = full.rsplit(".", 1)
        return ns, name
    return None, full


def char_to_line(text: str, idx: int) -> int:
    """Konverter tegnindeks til linjenummer (1-basert)."""
    return text.count("\n", 0, idx) + 1


def extract_brace_block(text: str, open_idx: int) -> Tuple[str, int, int]:
    """
    Gitt indeks til en '{' i `text`, returner innholdet inni blokken,
    samt start- og sluttindeks (eksklusiv slutt) for body.

    Returnerer:
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


def list_functions_with_code(text: str) -> List[Dict[str, Any]]:
    """
    Finn alle funksjoner i .ds-teksten og returner en liste med metadata + Deluge-kode.
    """
    out: List[Dict[str, Any]] = []

    for m in HEADER_RE.finditer(text):
        return_type = m.group(1)
        full = m.group(2)
        ns, name = split_name(full)

        header_idx = m.start()
        header_line = char_to_line(text, header_idx)

        # Finn første '{' etter headeren (etter parametere)
        brace_idx = text.find("{", m.end())
        if brace_idx == -1:
            # Ufullstendig definisjon – hopp over
            continue

        try:
            body, body_start, body_end = extract_brace_block(text, brace_idx)
        except ValueError:
            # Ubalanserte klammer – hopp over
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
            }
        )

    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksporter Deluge-funksjoner fra .ds-fil til JSON (inkl. funksjonskropp)."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Sti til .ds-filen",
    )
    parser.add_argument(
        "--out",
        default="functions_with_code.json",
        help="Filnavn for resultat (default: functions_with_code.json)",
    )
    args = parser.parse_args()

    text = read_text(args.file)
    funcs = list_functions_with_code(text)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(funcs, f, ensure_ascii=False, indent=2)

    print(f"{len(funcs)} funksjoner eksportert til {args.out}")


if __name__ == "__main__":
    main()
