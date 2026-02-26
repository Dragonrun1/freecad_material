# SPDX-FileCopyrightText: 2026 Michael Cummings
#
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Tests for fcmat.py — pytest unit tests.

Doctests live in the fcmat.py source docstrings and are discovered
automatically by xdoctest / pytest --doctest-modules.
"""
# ruff: noqa: D101, D102

from __future__ import annotations

import io
import textwrap
import uuid
from collections import OrderedDict

import pytest
from freecad_material import (
    FCMat,
    FCMatError,
    FCMatParseError,
    dump,
    dumps,
    load,
    loads,
    new_material,
)

# ---------------------------------------------------------------------------
# Fixtures & shared sample data
# ---------------------------------------------------------------------------

SIMPLE_FCM = textwrap.dedent("""\
    ---
    # A simple test material
    General:
      Name: "Gold test"
      UUID: "12345678-1234-5678-1234-567812345678"
      Author: "Test Author"
      License: "MIT OR Apache-2.0"
    Inherits:
      Gold:
        UUID: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
""")

BOM_FCM = "\ufeff" + SIMPLE_FCM


@pytest.fixture()
def simple_mat() -> FCMat:
    return FCMat.loads(SIMPLE_FCM)


# ---------------------------------------------------------------------------
# __all__ sanity
# ---------------------------------------------------------------------------


class TestPublicAPI:
    def test_all_exports_importable(self):
        import freecad_material as _mod

        for name in _mod.__all__:
            assert hasattr(_mod, name), (
                f"{name!r} listed in __all__ but not found"
            )

    def test_exception_hierarchy(self):
        assert issubclass(FCMatParseError, FCMatError)
        assert issubclass(FCMatError, Exception)


# ---------------------------------------------------------------------------
# FCMat is an OrderedDict
# ---------------------------------------------------------------------------


class TestInheritance:
    def test_is_ordered_dict(self, simple_mat):
        assert isinstance(simple_mat, OrderedDict)

    def test_is_fcmat(self, simple_mat):
        assert isinstance(simple_mat, FCMat)

    def test_sections_are_fcmat(self, simple_mat):
        assert isinstance(simple_mat["General"], FCMat)


# ---------------------------------------------------------------------------
# Parsing — FCMat.loads / loads()
# ---------------------------------------------------------------------------


class TestLoads:
    def test_loads_returns_fcmat(self):
        mat = loads(SIMPLE_FCM)
        assert isinstance(mat, FCMat)

    def test_top_level_sections_present(self, simple_mat):
        assert "General" in simple_mat
        assert "Inherits" in simple_mat

    def test_leaf_value(self, simple_mat):
        assert simple_mat["General"]["Name"] == "Gold test"

    def test_nested_section(self, simple_mat):
        assert (
            simple_mat["Inherits"]["Gold"]["UUID"]
            == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        )

    def test_bom_stripped(self):
        mat = FCMat.loads(BOM_FCM)
        assert "General" in mat

    def test_blank_lines_ignored(self):
        text = '---\n\nGeneral:\n\n  Name: "Test"\n'
        mat = FCMat.loads(text)
        assert mat["General"]["Name"] == "Test"

    def test_comment_lines_ignored(self):
        text = (
            '---\n# top comment\nGeneral:\n  # inner comment\n  Name: "Test"\n'
        )
        mat = FCMat.loads(text)
        assert mat["General"]["Name"] == "Test"

    def test_document_marker_ignored(self):
        mat = FCMat.loads('---\n---\nGeneral:\n  Name: "X"\n')
        assert mat["General"]["Name"] == "X"

    def test_unquoted_value(self):
        mat = FCMat.loads("---\nGeneral:\n  Name: NoQuotes\n")
        assert mat["General"]["Name"] == "NoQuotes"

    def test_quoted_value_strips_quotes(self):
        mat = FCMat.loads('---\nGeneral:\n  Name: "Quoted"\n')
        assert mat["General"]["Name"] == "Quoted"

    def test_value_with_escaped_quote(self):
        mat = FCMat.loads('---\nGeneral:\n  Name: "Say \\"Hi\\""\n')
        assert mat["General"]["Name"] == 'Say "Hi"'

    def test_insertion_order_preserved(self, simple_mat):
        assert list(simple_mat.keys()) == ["General", "Inherits"]

    def test_empty_document(self):
        mat = FCMat.loads("---\n")
        assert len(mat) == 0

    def test_module_level_loads_alias(self):
        mat = loads(SIMPLE_FCM)
        assert mat["General"]["Name"] == "Gold test"

    def test_parse_error_on_bad_indent(self):
        bad = '---\nGeneral:\n    Name: "X"\n   Bad: "Y"\n'
        with pytest.raises(FCMatParseError):
            FCMat.loads(bad)

    def test_parse_error_missing_colon(self):
        bad = '---\nGeneral\n  Name: "X"\n'
        with pytest.raises(FCMatParseError):
            FCMat.loads(bad)

    def test_parse_error_has_line_number(self):
        bad = '---\nGeneral\n  Name: "X"\n'
        with pytest.raises(FCMatParseError) as exc_info:
            FCMat.loads(bad)
        assert exc_info.value.line > 0

    def test_parse_error_line_zero_when_no_line(self):
        err = FCMatParseError("oops")
        assert err.line == 0

    def test_parse_error_message_includes_line(self):
        err = FCMatParseError("bad thing", line=7)
        assert "7" in str(err)
        assert "bad thing" in str(err)


# ---------------------------------------------------------------------------
# Parsing — FCMat.load / load()
# ---------------------------------------------------------------------------


class TestLoad:
    def test_load_from_path(self, tmp_path, simple_mat):
        p = tmp_path / "test.FCMat"
        p.write_text(SIMPLE_FCM, encoding="utf-8")
        mat = FCMat.load(str(p))
        assert mat["General"]["Name"] == "Gold test"

    def test_load_from_path_bom(self, tmp_path):
        p = tmp_path / "bom.FCMat"
        p.write_bytes(BOM_FCM.encode("utf-8-sig"))
        mat = FCMat.load(str(p))
        assert "General" in mat

    def test_load_from_text_io(self):
        fh = io.StringIO(SIMPLE_FCM)
        mat = FCMat.load(fh)
        assert mat["General"]["Name"] == "Gold test"

    def test_load_from_bytes_io(self):
        fh = io.BytesIO(SIMPLE_FCM.encode("utf-8"))
        mat = FCMat.load(fh)
        assert mat["General"]["Name"] == "Gold test"

    def test_module_level_load_alias(self, tmp_path):
        p = tmp_path / "test.FCMat"
        p.write_text(SIMPLE_FCM, encoding="utf-8")
        mat = load(str(p))
        assert mat["General"]["Name"] == "Gold test"


# ---------------------------------------------------------------------------
# Serialisation — FCMat.dumps / dumps()
# ---------------------------------------------------------------------------


class TestDumps:
    def test_dumps_returns_string(self, simple_mat):
        assert isinstance(simple_mat.dumps(), str)

    def test_dumps_starts_with_document_marker(self, simple_mat):
        assert simple_mat.dumps().startswith("---\n")

    def test_dumps_ends_with_newline(self, simple_mat):
        assert simple_mat.dumps().endswith("\n")

    def test_roundtrip_name(self, simple_mat):
        mat2 = FCMat.loads(simple_mat.dumps())
        assert mat2["General"]["Name"] == "Gold test"

    def test_roundtrip_nested(self, simple_mat):
        mat2 = FCMat.loads(simple_mat.dumps())
        assert (
            mat2["Inherits"]["Gold"]["UUID"]
            == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        )

    def test_default_header_comment(self, simple_mat):
        assert "# File written by freecad_material" in simple_mat.dumps()

    def test_custom_header_comment(self, simple_mat):
        assert "# My custom comment" in simple_mat.dumps(
            header_comment="My custom comment"
        )

    def test_custom_header_comment_without_hash(self, simple_mat):
        assert "# No hash here" in simple_mat.dumps(
            header_comment="No hash here"
        )

    def test_custom_header_comment_with_hash(self, simple_mat):
        out = simple_mat.dumps(header_comment="# Already hashed")
        assert "# Already hashed" in out
        assert "## Already hashed" not in out

    def test_empty_header_comment(self, simple_mat):
        lines = simple_mat.dumps(header_comment="").splitlines()
        assert not lines[1].startswith("#")

    def test_values_are_quoted(self, simple_mat):
        assert '"Gold test"' in simple_mat.dumps()

    def test_value_with_internal_quote_escaped(self):
        mat = FCMat()
        mat["General"] = FCMat()
        mat["General"]["Name"] = 'Say "Hi"'
        mat2 = FCMat.loads(mat.dumps())
        assert mat2["General"]["Name"] == 'Say "Hi"'

    def test_section_key_not_quoted(self, simple_mat):
        out = simple_mat.dumps()
        assert '"General"' not in out
        assert "General:" in out

    def test_module_level_dumps_alias(self, simple_mat):
        assert dumps(simple_mat) == simple_mat.dumps()

    def test_indentation_two_spaces(self, simple_mat):
        for line in simple_mat.dumps().splitlines():
            if "Name:" in line:
                assert line.startswith("  ")


# ---------------------------------------------------------------------------
# Serialisation — FCMat.dump / dump()
# ---------------------------------------------------------------------------


class TestDump:
    def test_dump_to_path(self, tmp_path, simple_mat):
        p = tmp_path / "out.FCMat"
        simple_mat.dump(str(p))
        assert p.exists()
        assert FCMat.load(str(p))["General"]["Name"] == "Gold test"

    def test_dump_to_text_io(self, simple_mat):
        fh = io.StringIO()
        simple_mat.dump(fh)
        fh.seek(0)
        assert FCMat.loads(fh.read())["General"]["Name"] == "Gold test"

    def test_dump_to_binary_io(self, fs, simple_mat):
        with open("/out.FCMat", "wb") as fh:
            simple_mat.dump(fh)
        with open("/out.FCMat", "r", encoding="utf-8") as fh:
            mat2 = FCMat.loads(fh.read())
        assert mat2["General"]["Name"] == "Gold test"

    def test_module_level_dump_alias(self, tmp_path, simple_mat):
        p = tmp_path / "out.FCMat"
        dump(simple_mat, str(p))
        assert load(str(p))["General"]["Name"] == "Gold test"


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------


class TestGetSection:
    def test_returns_fcmat_for_existing_section(self, simple_mat):
        assert isinstance(simple_mat.get_section("General"), FCMat)

    def test_returns_none_for_missing_section(self, simple_mat):
        assert simple_mat.get_section("Nonexistent") is None

    def test_returns_none_for_leaf_value(self):
        mat = FCMat()
        mat["Key"] = "value"
        assert mat.get_section("Key") is None


class TestGetValue:
    def test_returns_value(self, simple_mat):
        assert simple_mat.get_value("General", "Name") == "Gold test"

    def test_returns_default_for_missing_section(self, simple_mat):
        assert simple_mat.get_value("Missing", "Name") is None
        assert simple_mat.get_value("Missing", "Name", "fallback") == "fallback"

    def test_returns_default_for_missing_key(self, simple_mat):
        assert simple_mat.get_value("General", "Missing") is None
        assert simple_mat.get_value("General", "Missing", "fb") == "fb"

    def test_returns_default_for_non_leaf(self):
        mat = FCMat()
        mat["Section"] = FCMat()
        mat["Section"]["Sub"] = FCMat()
        assert mat.get_value("Section", "Sub", "default") == "default"


class TestSetValue:
    def test_sets_existing_value(self, simple_mat):
        simple_mat.set_value("General", "Name", "Platinum")
        assert simple_mat["General"]["Name"] == "Platinum"

    def test_creates_section_if_missing(self):
        mat = FCMat()
        mat.set_value("NewSection", "Key", "Val")
        assert mat["NewSection"]["Key"] == "Val"

    def test_created_section_is_fcmat(self):
        mat = FCMat()
        mat.set_value("NewSection", "Key", "Val")
        assert isinstance(mat["NewSection"], FCMat)

    def test_replaces_non_dict_section(self):
        mat = FCMat()
        mat["Section"] = "not a dict"
        mat.set_value("Section", "Key", "Val")
        assert mat["Section"]["Key"] == "Val"


# ---------------------------------------------------------------------------
# new_material()
# ---------------------------------------------------------------------------


class TestNewMaterial:
    def test_returns_fcmat(self):
        assert isinstance(new_material("Steel"), FCMat)

    def test_has_general_section(self):
        assert "General" in new_material("Steel")

    def test_name_set(self):
        assert new_material("Steel")["General"]["Name"] == "Steel"

    def test_uuid_is_valid(self):
        uid = new_material("Steel")["General"]["UUID"]
        assert str(uuid.UUID(uid)) == uid

    def test_uuid_unique_each_call(self):
        assert (
            new_material("A")["General"]["UUID"]
            != new_material("A")["General"]["UUID"]
        )

    def test_author_set_when_provided(self):
        assert (
            new_material("Steel", author="Alice")["General"]["Author"]
            == "Alice"
        )

    def test_author_absent_when_empty(self):
        assert "Author" not in new_material("Steel")["General"]

    def test_default_license(self):
        assert (
            new_material("Steel")["General"]["License"] == "MIT OR Apache-2.0"
        )

    def test_custom_license(self):
        assert (
            new_material("Steel", license_="MIT")["General"]["License"] == "MIT"
        )

    def test_new_material_roundtrips(self):
        mat = new_material("Gold", author="Bob")
        mat2 = FCMat.loads(mat.dumps())
        assert mat2["General"]["Name"] == "Gold"
        assert mat2["General"]["Author"] == "Bob"


# ---------------------------------------------------------------------------
# FCMatParseError details
# ---------------------------------------------------------------------------


class TestFCMatParseError:
    def test_message_without_line(self):
        err = FCMatParseError("something went wrong")
        assert "something went wrong" in str(err)
        assert err.line == 0

    def test_message_with_line(self):
        err = FCMatParseError("bad indent", line=42)
        assert "42" in str(err)
        assert "bad indent" in str(err)
        assert err.line == 42
