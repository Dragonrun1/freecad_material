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
    >>> # Roundtrip through string serialization
    >>> from freecad_material import loads, dumps
    >>> text = dumps(mat)
    >>> mat2 = loads(text)
    >>> mat2["General"]["Name"]
    'Gold'
"""

from collections import OrderedDict
import re
from typing import IO, Self
import uuid as _uuid

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
        line (int): The 1-based line number where the error occurred, or 0
            if the line is unknown.

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
        """Initializes FCMatParseError.

        Args:
            message (str): Human-readable description of the parse error.
            line (int): The 1-based line number where the error occurred.
                Defaults to 0 if unknown.
        """
        super().__init__(f"Line {line}: {message}" if line else message)
        self.line = line


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# noinspection SpellCheckingInspection
_DQUOTE_VALUE_RE = re.compile(r'^"(.*)"$')


def _unquote(value: str) -> str:
    r"""Remove surrounding double-quotes from a value string, if present,
    and unescape any internal escaped quotes and backslashes.

    Args:
        value (str): The raw value string from an FCMat file.

    Returns:
        str: The unquoted and unescaped string.

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

    Args:
        value (str): The plain string value to quote.

    Returns:
        str: The quoted and escaped string.

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
    """Return the number of leading spaces in a line.

    Args:
        line (str): A line of text from an FCMat file.

    Returns:
        int: The number of leading space characters.

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

    Top-level keys are section names (e.g. "General", "Inherits").
    Values are either:

    - A plain `str` (leaf value)
    - Another `FCMat` / `OrderedDict` (nested section)

    The class inherits from `OrderedDict` so the insertion order is
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
    def loads(cls, text: str) -> Self:
        r"""Parse a string and return an `FCMat` instance.

        Strips an optional UTF-8 BOM, skips `---` document markers,
        blank lines, and comment lines starting with `#`.

        Args:
            text (str): The FCMat file content as a string.

        Returns:
            FCMat: A parsed FCMat instance.

        Raises:
            FCMatParseError: If the text cannot be parsed.

        Example:
            >>> from freecad_material import FCMat
            >>> txt = "---\\nGeneral:\\n  Name: \\"Copper\\"\\n"
            >>> mat = FCMat.loads(txt)
            >>> mat["General"]["Name"]
            'Copper'
            >>> # BOM is handled transparently
            >>> mat2 = FCMat.loads("\\ufeff" + txt)
            >>> mat2["General"]["Name"]
            'Copper'
            >>> # Empty document is valid
            >>> FCMat.loads("---\\n")
            FCMat()
        """
        if text.startswith("\ufeff"):
            text = text[1:]
        lines = text.splitlines()
        return cls._parse(lines)

    @classmethod
    def load(cls, path_or_file: str | IO) -> Self:
        r"""Read from a path or file object and return an `FCMat` instance.

        Args:
            path_or_file (str | IO): A file path string, or a file-like
                object opened in text or binary mode.

        Returns:
            FCMat: A parsed FCMat instance.

        Raises:
            FCMatParseError: If the file content cannot be parsed.
            OSError: If the file cannot be opened.

        Example:
            >>> import io
            >>> from freecad_material import FCMat
            >>> txt = "---\\nGeneral:\\n  Name: \\"Iron\\"\\n"
            >>> fh1 = io.StringIO(txt)
            >>> mat = FCMat.load(fh1)
            >>> mat["General"]["Name"]
            'Iron'
            >>> # Also works with binary file-like objects
            >>> fh2 = io.BytesIO(txt.encode("utf-8"))
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
    # Serialization
    # ------------------------------------------------------------------

    def dumps(self, *, header_comment: str | None = None) -> str:
        r"""Serialize to a string.

        The output always starts with `---` and ends with a newline.
        All leaf values are wrapped in double-quotes with internal
        double-quotes and backslashes escaped.

        Args:
            header_comment (str | None): Optional comment line inserted
                after `---`. A leading `#` is added automatically if not
                present. Pass an empty string to suppress the comment
                entirely. Defaults to `"# File written by freecad_material"`.

        Returns:
            str: The serialized FCMat content.

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
            >>> lines_ = mat.dumps(header_comment="").splitlines()
            >>> lines_[1].startswith("#")
            False
        """
        lines: list[str] = ["---"]
        if header_comment is None:
            header_comment = "# File written by freecad_material"
        if header_comment:
            if not header_comment.startswith("#"):
                header_comment = "# " + header_comment
            lines.append(header_comment)
        self._serialize_dict(self, lines, indent=0)
        return "\n".join(lines) + "\n"

    def dump(self, path_or_file: str | IO, **kwargs) -> None:
        """Write to a path or file object.

        Args:
            path_or_file (str | IO): A file path string, or a file-like
                object opened in text or binary mode.
            **kwargs: Keyword arguments forwarded to `dumps`.

        Example:
            >>> import io
            >>> from freecad_material import FCMat
            >>> mat = FCMat()
            >>> mat["General"] = FCMat()
            >>> mat["General"]["Name"] = "Zinc"
            >>> fh1 = io.StringIO()
            >>> mat.dump(fh1)
            >>> _ = fh1.seek(0)
            >>> mat2 = FCMat.loads(fh1.read())
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

    def get_section(self, name: str) -> Self | None:
        """Return the named section as an `FCMat`, or `None`.

        Args:
            name (str): The section key to look up.

        Returns:
            FCMat | None: The section as an FCMat instance, or `None` if
                the key does not exist or its value is not a dict.

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
        self, section: str, key: str, default: str | None = None
    ) -> str | None:
        """Return a leaf value from a section key, or a default.

        Args:
            section (str): The top-level section key.
            key (str): The key within the section.
            default (str | None): Value to return when the section or key
                is absent, or when the value is not a plain string.
                Defaults to `None`.

        Returns:
            str | None: The string value, or `default`.

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

        If `section` does not exist, or exists but is not a dict, it is
        replaced with a new empty `FCMat`.

        Args:
            section (str): The top-level section key.
            key (str): The key within the section.
            value (str): The string value to set.

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
    def _parse(cls, lines: list[str]) -> Self:
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
        """Parse lines into a target dict at a given indent level.

        Stops when a line with a lesser indent is found without consuming it.

        Args:
            it (_LineIter): The peekable line iterator.
            target (FCMat): The dict to populate.
            expected_indent (int): The indentation level expected for this block.
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
    # Internal serialization
    # ------------------------------------------------------------------

    @classmethod
    def _serialize_dict(cls, d: dict, lines: list[str], indent: int) -> None:
        """Recursively serialize a dict into FCMat-formatted lines.

        Args:
            d (dict): The dictionary to serialize.
            lines (list[str]): The list of output lines to append to.
            indent (int): The current indentation level in spaces.
        """
        prefix = " " * indent
        for key, value in d.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                cls._serialize_dict(value, lines, indent + 2)
            else:
                lines.append(f"{prefix}{key}: {_quote(str(value))}")


# ---------------------------------------------------------------------------
# Internal line iterator
# ---------------------------------------------------------------------------


class _LineIter:
    """Simple peekable iterator over (line_number, line_text) pairs.

    Args:
        lines (list[str]): The list of lines to iterate over.
    """

    def __init__(self, lines: list[str]):
        """Initializes _LineIter.

        Args:
            lines (list[str]): The list of lines to iterate over.
        """
        self._lines = lines
        self._pos = 0

    def peek(self) -> tuple[int, str | None]:
        """Return the current (line_number, line_text) without advancing.

        Returns:
            tuple[int, str | None]: The 1-based line number and line text,
                or `None` for the text if the iterator is exhausted.
        """
        if self._pos >= len(self._lines):
            return self._pos + 1, None
        return self._pos + 1, self._lines[self._pos]

    def advance(self) -> str | None:
        """Consume and return the current line, or `None` if exhausted.

        Returns:
            str | None: The current line text, or `None` if exhausted.
        """
        if self._pos >= len(self._lines):
            return None
        line = self._lines[self._pos]
        self._pos += 1
        return line


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def load(path_or_file: str | IO) -> FCMat:
    r"""Read an FCMat file and return an `FCMat` instance.

    Args:
        path_or_file (str | IO): A file path string, or a file-like object.

    Returns:
        FCMat: A parsed FCMat instance.

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
    r"""Parse an FCMat string and return an `FCMat` instance.

    Args:
        text (str): The FCMat file content as a string.

    Returns:
        FCMat: A parsed FCMat instance.

    Example:
        >>> from freecad_material import loads
        >>> mat = loads("---\\nGeneral:\\n  Name: \\"Cobalt\\"\\n")
        >>> mat["General"]["Name"]
        'Cobalt'
    """
    return FCMat.loads(text)


def dump(mat: FCMat, path_or_file: str | IO, **kwargs) -> None:
    """Write an FCMat instance to a file.

    Args:
        mat (FCMat): The FCMat instance to serialize.
        path_or_file (str | IO): A file path string, or a file-like object.
        **kwargs: Keyword arguments forwarded to `FCMat.dumps`.

    Example:
        >>> import io
        >>> from freecad_material import dump, load, new_material
        >>> mat_ = new_material("Chrome")
        >>> fh = io.StringIO()
        >>> dump(mat_, fh)
        >>> _ = fh.seek(0)
        >>> load(fh)["General"]["Name"]
        'Chrome'
    """
    mat.dump(path_or_file, **kwargs)


def dumps(mat: FCMat, **kwargs) -> str:
    """Serialize an FCMat instance to a string.

    Args:
        mat (FCMat): The FCMat instance to serialize.
        **kwargs: Keyword arguments forwarded to `FCMat.dumps`.

    Returns:
        str: The serialized FCMat content.

    Example:
        >>> from freecad_material import dumps, loads, new_material
        >>> mat_ = new_material("Silver")
        >>> text = dumps(mat_)
        >>> loads(text)["General"]["Name"]
        'Silver'
    """
    return mat.dumps(**kwargs)


def new_material(
    name: str, author: str = "", license_: str = "MIT OR Apache-2.0"
) -> FCMat:
    """Create a minimal FCMat with a freshly generated UUID and metadata.

    A new UUID is generated on every call.

    Args:
        name (str): Material name.
        author (str): Author string. Omitted from the output if empty.
        license_ (str): License string. Defaults to `"MIT OR Apache-2.0"`.

    Returns:
        FCMat: A new FCMat instance with a `General` section populated.

    Example:
        >>> from freecad_material import new_material
        >>> import uuid
        >>> mat_ = new_material("Titanium", author="Bob", license_="MIT")
        >>> mat_["General"]["Name"]
        'Titanium'
        >>> mat_["General"]["Author"]
        'Bob'
        >>> mat_["General"]["License"]
        'MIT'
        >>> # UUID is a valid UUID4
        >>> uid = uuid.UUID(mat_["General"]["UUID"])
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
