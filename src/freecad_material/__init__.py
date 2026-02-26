# SPDX-FileCopyrightText: 2026 Michael Cummings
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Pure Python library for reading and writing FreeCAD FCMat material files."""

from .fcmat import (
    FCMat,
    FCMatError,
    FCMatParseError,
    dump,
    dumps,
    load,
    loads,
    new_material,
)

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
