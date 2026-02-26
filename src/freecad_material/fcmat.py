# SPDX-FileCopyrightText: 2026 Michael Cummings
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""fcmat.py - Pure Python library for reading and writing FreeCAD FCMat material
files.

FreeCAD 1.0.2+ material files use a YAML-like format with:
  - Optional BOM (UTF-8 with BOM)
  - YAML document start marker (---)
  - Optional comment lines starting with #
  - Nested key-value structure with 2-space indentation
  - String values quoted with double quotes
  - No multi-document support

Usage:
    from freecad_material import FCMat, load, loads, new_material

    # Read a file
    mat = FCMat.load("Gold.FCMat")

    # Access sections
    print(mat["General"]["Name"]) # "Gold test"
    print(mat["Inherits"]["Gold"]["UUID"])

    # Modify values
    mat["General"]["Name"] = "Platinum"

    # Write a file
    mat.dump("Platinum.FCMat")

    # Or work with strings
    text = mat.dumps()
    mat2 = FCMat.loads(text)
"""

import re
import uuid as _uuid
from collections import OrderedDict
from typing import IO, Optional, Union

__all__ = [
    "FCMat",
    "FCMatError",
    "FCMatParseError",
    "load",
    "loads",
    "dump",
    "dumps",
    "new_material",
]

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FCMatError(Exception):
    """Base exception for FCMat errors."""


class FCMatParseError(FCMatError):
    """Raised when a file cannot be parsed."""

    def __init__(self, message: str, line: int = 0):
        """Xx."""
        super().__init__(f"Line {line}: {message}" if line else message)
        self.line = line


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DQUOTE_VALUE_RE = re.compile(r'^"(.*)"$')


def _unquote(value: str) -> str:
    """Remove surrounding double-quotes from a value string, if present."""
    m = _DQUOTE_VALUE_RE.match(value)
    return m.group(1) if m else value


def _quote(value: str) -> str:
    """Wrap a value in double-quotes, escaping any internal double-quotes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _indent_level(line: str) -> int:
    """Return the number of leading spaces in *line*."""
    return len(line) - len(line.lstrip(" "))


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------


class FCMat(OrderedDict):
    """Represents a FreeCAD FCMat material file as an ordered dictionary.

    Top-level keys are section names (e.g. ``"General"``, ``"Inherits"``).
    Values are either:
      - A plain ``str`` (leaf value)
      - Another ``FCMat`` / ``OrderedDict`` (nested section)

    The class inherits from ``OrderedDict`` so the insertion order is preserved,
    and the sections/keys can be accessed and mutated like a normal dict.
    """

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def loads(cls, text: str) -> "FCMat":
        """Parse *text* (a ``str``) and return an ``FCMat`` instance."""
        # Strip UTF-8 BOM if present
        if text.startswith("\ufeff"):
            text = text[1:]
        lines = text.splitlines()
        return cls._parse(lines)

    @classmethod
    def load(cls, path_or_file: Union[str, IO]) -> "FCMat":
        """Read from *path_or_file* and return an ``FCMat`` instance."""
        if isinstance(path_or_file, str):
            with open(path_or_file, encoding="utf-8-sig") as fh:
                text = fh.read()
        else:
            text = path_or_file.read()
            if isinstance(text, bytes):
                text = text.decode("utf-8-sig")
        return cls.loads(text)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def dumps(self, *, header_comment: Optional[str] = None) -> str:
        """Serialize to a string.

        Parameters
        ----------
        header_comment:
            Optional comment line inserted after ``---``.
            Defaults to a generic FreeCAD-style comment if *None*.
        """
        # document start
        lines: list[str] = ["---"]
        if header_comment is None:
            header_comment = "# File written by freecad_material"
        if header_comment:
            if not header_comment.startswith("#"):
                header_comment = "# " + header_comment
            lines.append(header_comment)
        self._serialise_dict(self, lines, indent=0)
        return "\n".join(lines) + "\n"

    def dump(self, path_or_file: Union[str, IO], **kwargs) -> None:
        """Write to *path_or_file*.
        Keyword arguments are forwarded to ``dumps``.
        """
        text = self.dumps(**kwargs)
        if isinstance(path_or_file, str):
            with open(path_or_file, "w", encoding="utf-8") as fh:
                fh.write(text)
        else:
            if hasattr(path_or_file, "mode") and "b" in getattr(
                path_or_file, "mode", ""
            ):
                path_or_file.write(text.encode("utf-8"))
            else:
                path_or_file.write(text)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def get_section(self, name: str) -> Optional["FCMat"]:
        """Return the named section as an ``FCMat``, or ``None``."""
        val = self.get(name)
        if isinstance(val, FCMat):
            return val
        return None

    def get_value(
        self, section: str, key: str, default: Optional[str] = None
    ) -> Optional[str]:
        """Return a leaf value from ``section[key]``, or *default*."""
        sec = self.get_section(section)
        if sec is None:
            return default
        val = sec.get(key)
        if val is None:
            return default
        if isinstance(val, str):
            return val
        return default

    def set_value(self, section: str, key: str, value: str) -> None:
        """Set a leaf value, creating the section if necessary."""
        if section not in self or not isinstance(self[section], dict):
            self[section] = FCMat()
        self[section][key] = value

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    @classmethod
    def _parse(cls, lines: list[str]) -> "FCMat":
        root = cls()
        # Skip BOM line / YAML document marker / comment lines
        # We do a simple state-machine parser.
        it = _LineIter(lines)
        try:
            cls._parse_block(it, root, expected_indent=0)
        except FCMatParseError:
            raise
        except Exception as exc:
            raise FCMatParseError(str(exc)) from exc
        return root

    @classmethod
    def _parse_block(
        cls, it: "_LineIter", target: "FCMat", expected_indent: int
    ) -> None:
        """Parse lines into *target* dict at *expected_indent* level.
        Stops when a line is found with a lesser indent (does not consume it).
        """
        while True:
            line_no, raw = it.peek()
            if raw is None:
                return  # EOF

            # Skip blank lines, comments, document markers
            stripped = raw.strip()
            if not stripped or stripped.startswith("#") or stripped == "---":
                it.advance()
                continue

            indent = _indent_level(raw)
            if indent < expected_indent:
                # Belongs to an outer block — stop without consuming
                return
            if indent > expected_indent:
                raise FCMatParseError(
                    f"Unexpected indentation (got {indent},"
                    f" expected {expected_indent})",
                    line_no,
                )

            # Consume this line
            it.advance()

            # Must be a "key: value" or "key:" line
            if ":" not in stripped:
                raise FCMatParseError(
                    f"Expected 'key: value' but got: {raw!r}", line_no
                )

            colon_pos = stripped.index(":")
            key = stripped[:colon_pos].strip()
            rest = stripped[colon_pos + 1 :].strip()

            if rest:
                # Leaf value
                target[key] = _unquote(rest)
            else:
                # Nested block
                child = cls()
                target[key] = child
                cls._parse_block(it, child, expected_indent=expected_indent + 2)

    # ------------------------------------------------------------------
    # Internal serialisation
    # ------------------------------------------------------------------

    @classmethod
    def _serialise_dict(cls, d: dict, lines: list[str], indent: int) -> None:
        prefix = " " * indent
        for key, value in d.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                cls._serialise_dict(value, lines, indent + 2)
            else:
                lines.append(f"{prefix}{key}: {_quote(str(value))}")


# ---------------------------------------------------------------------------
# Internal line iterator
# ---------------------------------------------------------------------------


class _LineIter:
    """Simple peekable iterator over (line_number, line_text) pairs."""

    def __init__(self, lines: list[str]):
        self._lines = lines
        self._pos = 0

    def peek(self) -> tuple[int, Optional[str]]:
        if self._pos >= len(self._lines):
            return self._pos + 1, None
        return self._pos + 1, self._lines[self._pos]

    def advance(self) -> Optional[str]:
        if self._pos >= len(self._lines):
            return None
        line = self._lines[self._pos]
        self._pos += 1
        return line


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def load(path_or_file: Union[str, IO]) -> FCMat:
    """Read an FCMat file and return an :class:`FCMat` instance."""
    return FCMat.load(path_or_file)


def loads(text: str) -> FCMat:
    """Parse an FCMat string and return an :class:`FCMat` instance."""
    return FCMat.loads(text)


def dump(mat: FCMat, path_or_file: Union[str, IO], **kwargs) -> None:
    """Write *mat* to a file."""
    mat.dump(path_or_file, **kwargs)


def dumps(mat: FCMat, **kwargs) -> str:
    """Serialize *mat* to a string."""
    return mat.dumps(**kwargs)


def new_material(
    name: str, author: str = "", license_: str = "MIT OR Apache-2.0"
) -> FCMat:
    """Create a minimal FCMat with a freshly generated UUID and the given
    metadata.

    Parameters
    ----------
    name:    Material name.
    author:  Author string.
    license_: License string (default ``"MIT OR Apache-2.0"``).
    """
    mat = FCMat()
    mat["General"] = FCMat()
    mat["General"]["UUID"] = str(_uuid.uuid4())
    mat["General"]["Name"] = name
    if author:
        mat["General"]["Author"] = author
    mat["General"]["License"] = license_
    return mat
