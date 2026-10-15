from __future__ import annotations

import re
import unicodedata
from html import escape as html_escape

# Characters where unicodedata.normalize() has not the desired result.
# Extend the table when content introduces a letter it does not cover yet.
# Only uppercase, the lowercase is deduced below.
_SPELLED_LETTERS = {
    "Ä": "Ae",
    "Ö": "Oe",
    "Ü": "Ue",
    "ẞ": "Ss",
    "Æ": "Ae",
    "Œ": "Oe",
    "Ø": "O",
    "Ð": "Dh",
    "Þ": "Th",
}
_SPELLED_LETTERS |= {c.lower(): s.lower() for c, s in _SPELLED_LETTERS.items()}
_SPELLED_LETTERS = {ord(c): s for c, s in _SPELLED_LETTERS.items()}


# Retained as a general utility; unreferenced since legacy user resolution was removed.
def to_ascii(value: str) -> str:
    """Return ``value`` transliterated to ASCII, preserving case.

    The spelling table is applied first, Unicode decomposition then removes the
    remaining marks, and anything still outside ASCII is replaced.
    """
    value = value.translate(_SPELLED_LETTERS)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return value.encode("ascii", errors="replace").decode("ascii")


def render_markdown_template(template_text: str, replacements: dict[str, str]) -> str:
    """Replace template placeholders once while preserving block indentation.

    A replacement value is content, not another template: placeholder-shaped
    text inside a generated value remains unchanged.
    """
    if not replacements:
        return template_text

    placeholders = "|".join(
        re.escape(placeholder)
        for placeholder in sorted(replacements, key=len, reverse=True)
    )
    pattern = re.compile(
        rf"(?m)^(?P<indent>[ \t]*)(?P<block>{placeholders})(?P<trailing>[ \t]*)$"
        rf"|(?P<inline>{placeholders})"
    )

    def replace(match: re.Match[str]) -> str:
        placeholder = match.group("block") or match.group("inline")
        value = replacements[placeholder]
        indentation = match.group("indent")
        if indentation is None:
            return value

        indented_lines = [
            f"{indentation}{line}" if line else indentation
            for line in value.split("\n")
        ]
        return "\n".join(indented_lines) + match.group("trailing")

    return pattern.sub(replace, template_text)


def render_headless_key_value_table(
    rows: list[tuple[str, str]],
    *,
    escape_values: bool = True,
) -> list[str]:
    """Return semantic HTML for a two-column table without a header row.

    Set ``escape_values`` to ``False`` only for trusted, renderer-owned HTML.
    """
    lines = ["<table>", "<tbody>"]
    for key, value in rows:
        safe_key = html_escape(key)
        safe_value = html_escape(value) if escape_values else value
        safe_value = safe_value or "-"
        lines.append(f"<tr><td>{safe_key}</td><td>{safe_value}</td></tr>")
    lines.extend(["</tbody>", "</table>"])
    return lines
