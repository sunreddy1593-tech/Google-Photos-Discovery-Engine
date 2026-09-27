"""Syntax-only JSON cleanup.

Allowed edits are a surrounding code fence, a trailing comma, and a smart
quote used as a delimiter. A string's characters, a number, a field, and an
enum token are left as the model wrote them. Invalid values fail validation
afterwards; this module does not correct them.
"""

from __future__ import annotations

import json
from typing import Any

_FENCE = "```"


def parse_json_document(text: str) -> tuple[Any, bool]:
    """Parse ``text``. The boolean is true when syntax cleanup was required.

    Raises ``json.JSONDecodeError`` when the text is still not JSON. Callers
    map that to ``response_parse_failed``. A preamble is not stripped: picking
    one object out of surrounding prose would choose a value.
    """
    stripped = text.strip().lstrip("\ufeff")
    fenced = _strip_fence(stripped)
    try:
        return json.loads(fenced), fenced != stripped
    except json.JSONDecodeError:
        fixed = _repair_syntax(fenced)
        # json.loads raises if the repair was not enough. The raised error is
        # the caller's signal to stop; there is no second, looser parse.
        return json.loads(fixed), True


def _strip_fence(text: str) -> str:
    if not text.startswith(_FENCE):
        return text
    rest = text[len(_FENCE) :]
    newline = rest.find("\n")
    if newline == -1:
        return text
    body = rest[newline + 1 :]
    if body.rstrip().endswith(_FENCE):
        body = body.rstrip()[: -len(_FENCE)].rstrip()
    return body


def _repair_syntax(text: str) -> str:
    """Drop trailing commas and treat curly double quotes as JSON delimiters."""
    out: list[str] = []
    in_string = False
    delim = ""
    escape = False
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if in_string:
            out.append('"' if char == "”" and delim == "“" else char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif delim == '"' and char == '"':
                in_string = False
            elif delim == "“" and char == "”":
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            delim = '"'
            out.append(char)
            index += 1
            continue
        if char == "“":
            in_string = True
            delim = "“"
            out.append('"')
            index += 1
            continue
        if char == ",":
            look = index + 1
            while look < length and text[look] in " \t\r\n":
                look += 1
            if look < length and text[look] in "}]":
                index += 1
                continue
        out.append(char)
        index += 1
    return "".join(out)
