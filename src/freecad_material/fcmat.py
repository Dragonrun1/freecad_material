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

Example:
    >>> from freecad_material import FCMat, new_material
    >>> # Create a new material
    >>> mat = new_material("Gold", author="Alice")
    >>> mat["General"]["Name"]
    'Gold'
    >>> mat["General"]["Author"]
    'Alice'
    >>> mat["General"]["License"]
    'MIT OR Apache-2.0'
    >>> # Roundtrip through string serialisation
    >>> from freecad_material import loads, dumps
    >>> text = dumps(mat)
    >>> mat2 = loads(text)
    >>> mat2["General"]["Name"]
    'Gold'
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
    """Raised when a file cannot be parsed.

    Attributes:
        line: The 1-based line number where the error occurred, or 0 if
            the line is unknown.

    Example:
        >>> from freecad_material import FCMatParseError
        >>> err = FCMatParseError("bad indent", line=5)
        >>> err.line
        5
        >>> "5" in str(err)
        True
        >>> err2 = FCMatParseError("unknown error")
        >>> err2.line
        0
    """

    def __init__(self, message: str, line: int = 0):
        """Xx."""
        super().__init__(f"Line {line}: {message}" if line else message)
        self.line = line


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DQUOTE_VALUE_RE = re.compile(r'^"(.*)"$')


def _unquote(value: str) -> str:
    r"""Remove surrounding double-quotes from a value string, if present,
    and unescape any internal escaped quotes and backslashes.

    Example:
        >>> _unquote('"hello"')
        'hello'
        >>> _unquote("no quotes")
        'no quotes'
        >>> _unquote('"Say, \\\\"Hi\\\\""')
        'Say, "Hi"'
        >>> _unquote('""')
        ''
    """
    m = _DQUOTE_VALUE_RE.match(value)
    if not m:
        return value
    inner = m.group(1)
    # Unescape \" -> " and \\ -> \ (order matters — reverse of _quote)
    return inner.replace('\\"', '"').replace("\\\\", "\\")


def _quote(value: str) -> str:
    r"""Wrap a value in double-quotes, escaping any internal double-quotes
    and backslashes.

    Example:
        >>> _quote("hello")
        '"hello"'
        >>> _quote('Say "Hi"')
        '"Say \\\\"Hi\\\\""'
        >>> _quote("")
        '""'
        >>> _quote("back\\\\slash")
        '"back\\\\\\\\slash"'
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _indent_level(line: str) -> int:
    """Return the number of leading spaces in *line*.

    Example:
        >>> _indent_level("no indent")
        0
        >>> _indent_level("  two spaces")
        2
        >>> _indent_level("    four spaces")
        4
        >>> _indent_level("")
        0
    """
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

    The class inherits from ``OrderedDict`` so the insertion order is
    preserved, and the sections/keys can be accessed and mutated like a
    normal dict.

    Example:
        >>> from freecad_material import FCMat
        >>> mat = FCMat()
        >>> isinstance(mat, dict)
        True
        >>> mat["General"] = FCMat()
        >>> mat["General"]["Name"] = "Steel"
        >>> mat["General"]["Name"]
        'Steel'
    """

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def loads(cls, text: str) -> "FCMat":
        r"""Parse *text* (a ``str``) and return an ``FCMat`` instance.

        Strips an optional UTF-8 BOM, skips ``---`` document markers,
        blank lines, and comment lines starting with ``#``.

        Args:
            text: The FCMat file content as a string.

        Returns:
            A parsed ``FCMat`` instance.

        Raises:
            FCMatParseError: If the text cannot be parsed.

        Example:
            >>> from freecad_material import FCMat
            >>> text = "---\\nGeneral:\\n  Name: \\"Copper\\"\\n"
            >>> mat = FCMat.loads(text)
            >>> mat["General"]["Name"]
            'Copper'
            >>> # BOM is handled transparently
            >>> mat2 = FCMat.loads("\\ufeff" + text)
            >>> mat2["General"]["Name"]
            'Copper'
            >>> # Empty document is valid
            >>> FCMat.loads("---\\n")
            FCMat()
        """
        # Strip UTF-8 BOM if present
        if text.startswith("\ufeff"):
            text = text[1:]
        lines = text.splitlines()
        return cls._parse(lines)

    @classmethod
    def load(cls, path_or_file: Union[str, IO]) -> "FCMat":
        r"""Read from *path_or_file* and return an ``FCMat`` instance.

        Args:
            path_or_file: A file path string, or a file-like object opened
                in text or binary mode.

        Returns:
            A parsed ``FCMat`` instance.

        Raises:
            FCMatParseError: If the file content cannot be parsed.
            OSError: If the file cannot be opened.

        Example:
            >>> import io
            >>> from freecad_material import FCMat
            >>> text = "---\\nGeneral:\\n  Name: \\"Iron\\"\\n"
            >>> fh = io.StringIO(text)
            >>> mat = FCMat.load(fh)
            >>> mat["General"]["Name"]
            'Iron'
            >>> # Also works with binary file-like objects
            >>> fh2 = io.BytesIO(text.encode("utf-8"))
            >>> mat2 = FCMat.load(fh2)
            >>> mat2["General"]["Name"]
            'Iron'
        """
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
        r"""Serialize to a string.

        The output always starts with ``---`` and ends with a newline.
        All leaf values are wrapped in double-quotes with internal
        double-quotes and backslashes escaped.

        Args:
            header_comment: Optional comment line inserted after ``---``.
                A leading ``#`` is added automatically if not present.
                Pass an empty string to suppress the comment entirely.
                Defaults to ``"# File written by freecad_material"``.

        Returns:
            The serialised FCMat content as a string.

        Example:
            >>> from freecad_material import FCMat
            >>> mat = FCMat()
            >>> mat["General"] = FCMat()
            >>> mat["General"]["Name"] = "Tin"
            >>> out = mat.dumps()
            >>> out.startswith("---\\n")
            True
            >>> out.endswith("\\n")
            True
            >>> '"Tin"' in out
            True
            >>> # Roundtrip
            >>> mat2 = FCMat.loads(out)
            >>> mat2["General"]["Name"]
            'Tin'
            >>> # Custom header comment
            >>> "# My note" in mat.dumps(header_comment="My note")
            True
            >>> # Suppress header comment
            >>> lines = mat.dumps(header_comment="").splitlines()
            >>> lines[1].startswith("#")
            False
        """
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

        Args:
            path_or_file: A file path string, or a file-like object opened
                in text or binary mode.
            **kwargs: Keyword arguments forwarded to :meth:`dumps`.

        Example:
            >>> import io
            >>> from freecad_material import FCMat
            >>> mat = FCMat()
            >>> mat["General"] = FCMat()
            >>> mat["General"]["Name"] = "Zinc"
            >>> fh = io.StringIO()
            >>> mat.dump(fh)
            >>> _ = fh.seek(0)
            >>> mat2 = FCMat.loads(fh.read())
            >>> mat2["General"]["Name"]
            'Zinc'
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
        """Return the named section as an ``FCMat``, or ``None``.

        Args:
            name: The section key to look up.

        Returns:
            The section as an ``FCMat`` instance, or ``None`` if the key
            does not exist or its value is not a dict.

        Example:
            >>> from freecad_material import FCMat
            >>> mat = FCMat()
            >>> mat.set_value("Props", "Color", "Blue")
            >>> sec = mat.get_section("Props")
            >>> isinstance(sec, FCMat)
            True
            >>> mat.get_section("Missing") is None
            True
            >>> # Leaf values are not returned as sections
            >>> mat["Leaf"] = "just a string"
            >>> mat.get_section("Leaf") is None
            True
        """
        val = self.get(name)
        if isinstance(val, FCMat):
            return val
        return None

    def get_value(
        self, section: str, key: str, default: Optional[str] = None
    ) -> Optional[str]:
        """Return a leaf value from ``section[key]``, or *default*.

        Args:
            section: The top-level section key.
            key: The key within the section.
            default: Value to return when the section or key is absent,
                or when the value is not a plain string. Defaults to
                ``None``.

        Returns:
            The string value, or *default*.

        Example:
            >>> from freecad_material import FCMat
            >>> mat = FCMat()
            >>> mat.set_value("General", "Name", "Iron")
            >>> mat.get_value("General", "Name")
            'Iron'
            >>> mat.get_value("General", "Missing") is None
            True
            >>> mat.get_value("General", "Missing", "fallback")
            'fallback'
            >>> mat.get_value("NoSection", "Key", "fb")
            'fb'
        """
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
        """Set a leaf value, creating the section if necessary.

        If *section* does not exist, or exists but is not a dict, it is
        replaced with a new empty ``FCMat``.

        Args:
            section: The top-level section key.
            key: The key within the section.
            value: The string value to set.

        Example:
            >>> from freecad_material import FCMat
            >>> mat = FCMat()
            >>> mat.set_value("General", "Name", "Lead")
            >>> mat["General"]["Name"]
            'Lead'
            >>> # Section is created automatically
            >>> "General" in mat
            True
            >>> isinstance(mat["General"], FCMat)
            True
            >>> # Existing values are overwritten
            >>> mat.set_value("General", "Name", "Tin")
            >>> mat["General"]["Name"]
            'Tin'
        """
        if section not in self or not isinstance(self[section], dict):
            self[section] = FCMat()
        self[section][key] = value

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    @classmethod
    def _parse(cls, lines: list[str]) -> "FCMat":
        root = cls()
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
    r"""Read an FCMat file and return an :class:`FCMat` instance.

    Args:
        path_or_file: A file path string, or a file-like object.

    Returns:
        A parsed ``FCMat`` instance.

    Example:
        >>> import io
        >>> from freecad_material import load
        >>> fh = io.StringIO("---\\nGeneral:\\n  Name: \\"Nickel\\"\\n")
        >>> mat = load(fh)
        >>> mat["General"]["Name"]
        'Nickel'
    """
    return FCMat.load(path_or_file)


def loads(text: str) -> FCMat:
    r"""Parse an FCMat string and return an :class:`FCMat` instance.

    Args:
        text: The FCMat file content as a string.

    Returns:
        A parsed ``FCMat`` instance.

    Example:
        >>> from freecad_material import loads
        >>> mat = loads("---\\nGeneral:\\n  Name: \\"Cobalt\\"\\n")
        >>> mat["General"]["Name"]
        'Cobalt'
    """
    return FCMat.loads(text)


def dump(mat: FCMat, path_or_file: Union[str, IO], **kwargs) -> None:
    """Write *mat* to a file.

    Args:
        mat: The ``FCMat`` instance to serialise.
        path_or_file: A file path string, or a file-like object.
        **kwargs: Keyword arguments forwarded to :meth:`FCMat.dumps`.

    Example:
        >>> import io
        >>> from freecad_material import dump, load, new_material
        >>> mat = new_material("Chrome")
        >>> fh = io.StringIO()
        >>> dump(mat, fh)
        >>> _ = fh.seek(0)
        >>> load(fh)["General"]["Name"]
        'Chrome'
    """
    mat.dump(path_or_file, **kwargs)


def dumps(mat: FCMat, **kwargs) -> str:
    """Serialize *mat* to a string.

    Args:
        mat: The ``FCMat`` instance to serialise.
        **kwargs: Keyword arguments forwarded to :meth:`FCMat.dumps`.

    Returns:
        The serialised FCMat content as a string.

    Example:
        >>> from freecad_material import dumps, loads, new_material
        >>> mat = new_material("Silver")
        >>> text = dumps(mat)
        >>> loads(text)["General"]["Name"]
        'Silver'
    """
    return mat.dumps(**kwargs)


def new_material(
    name: str, author: str = "", license_: str = "MIT OR Apache-2.0"
) -> FCMat:
    """Create a minimal FCMat with a freshly generated UUID and the given
    metadata.

    A new UUID is generated on every call.

    Args:
        name: Material name.
        author: Author string. Omitted from the output if empty.
        license_: License string. Defaults to ``"MIT OR Apache-2.0"``.

    Returns:
        A new ``FCMat`` instance with a ``General`` section populated.

    Example:
        >>> from freecad_material import new_material
        >>> import uuid
        >>> mat = new_material("Titanium", author="Bob", license_="MIT")
        >>> mat["General"]["Name"]
        'Titanium'
        >>> mat["General"]["Author"]
        'Bob'
        >>> mat["General"]["License"]
        'MIT'
        >>> # UUID is a valid UUID4
        >>> uid = uuid.UUID(mat["General"]["UUID"])
        >>> uid.version
        4
        >>> # Author is absent when not supplied
        >>> "Author" not in new_material("X")["General"]
        True
        >>> # Each call produces a unique UUID
        >>> new_material("A")["General"]["UUID"] != new_material("A")[
        ...     "General"
        ... ]["UUID"]
        True
    """
    mat = FCMat()
    mat["General"] = FCMat()
    mat["General"]["UUID"] = str(_uuid.uuid4())
    mat["General"]["Name"] = name
    if author:
        mat["General"]["Author"] = author
    mat["General"]["License"] = license_
    return mat
