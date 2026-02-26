<!--
SPDX-FileCopyrightText: 2026 Michael Cummings

SPDX-License-Identifier: MIT OR Apache-2.0
-->

# freecad-material

Pure Python library for reading, writing, and manipulating [FreeCAD](https://www.freecad.org/) FCMat material files with full round-trip fidelity.

FreeCAD 1.0.0+ stores material definitions in a YAML-like `.FCMat` format. This library parses those files into ordinary Python dictionaries, lets you inspect and modify them, and writes them back out in a format that FreeCAD accepts.

## Features

- Pure Python — no dependencies outside the standard library
- Full round-trip fidelity: files written by this library are accepted by FreeCAD
- Preserves insertion order of sections and keys
- Handles UTF-8 BOM transparently
- Typed — ships a `py.typed` marker for use with mypy and pyright
- Simple, Pythonic API

## Installation

```bash
pip install freecad-material
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add freecad-material
```

## Quick Start

```python
from freecad_material import FCMat, load, loads, new_material

# Read a file from disk
mat = load("Aluminum.FCMat")

# Access sections and values
print(mat["General"]["Name"])                              # "Aluminum"
print(mat["AppearanceModels"]["Basic Rendering"]["Shininess"])  # "0.09"

# Modify a value
mat["General"]["Author"] = "Jane Smith"

# Add a value to an existing section
mat.set_value("General", "Description", "Custom aluminum alloy")

# Write back to disk
mat.dump("Aluminum.FCMat")
```

## Parsing from a String

```python
from freecad_material import loads, dumps

text = """---
# File created by FreeCAD 1.0.2
General:
  UUID: "1d8534f9-83cf-4524-be9a-e37eed281f76"
  Name: "Aluminum"
  License: "GPL-2.0-or-later"
AppearanceModels:
  Basic Rendering:
    UUID: "f006c7e4-35b7-43d5-bbf9-c5d572309e6e"
    Shininess: "0.09"
    Transparency: "0"
"""

mat = loads(text)
print(mat["General"]["Name"])  # "Aluminum"

# Serialize back to a string
output = dumps(mat)
```

## Creating a New Material

```python
from freecad_material import new_material

mat = new_material("Platinum", author="Jane Smith")

# A UUID is generated automatically
print(mat["General"]["UUID"])   # e.g. "a1b2c3d4-..."
print(mat["General"]["License"])  # "MIT OR Apache-2.0"

# Add appearance properties
mat.set_value("AppearanceModels", "Basic Rendering", "")
mat["AppearanceModels"]["Basic Rendering"] = {
    "UUID": "f006c7e4-35b7-43d5-bbf9-c5d572309e6e",
    "Shininess": "0.06",
    "Transparency": "0",
}

mat.dump("Platinum.FCMat")
```

## API Reference

### `FCMat`

Subclass of `OrderedDict` representing a parsed FCMat file. Top-level keys are section names; values are either a nested `FCMat` (a section) or a `str` (a leaf value).

| Method                                 | Description                                         |
|----------------------------------------|-----------------------------------------------------|
| `FCMat.load(path_or_file)`             | Parse an FCMat file from a path or open file object |
| `FCMat.loads(text)`                    | Parse an FCMat file from a string                   |
| `mat.dump(path_or_file)`               | Write to a path or open file object                 |
| `mat.dumps()`                          | Serialise to a string                               |
| `mat.get_section(name)`                | Return a named section as `FCMat`, or `None`        |
| `mat.get_value(section, key, default)` | Return a leaf value, or `default`                   |
| `mat.set_value(section, key, value)`   | Set a leaf value, creating the section if needed    |

### Module-level convenience functions

```python
load(path_or_file)       # → FCMat
loads(text)              # → FCMat
dump(mat, path_or_file)  # → None
dumps(mat)               # → str
new_material(name, author="", license_="MIT OR Apache-2.0")  # → FCMat
```

### Exceptions

| Exception         | Description                                       |
|-------------------|---------------------------------------------------|
| `FCMatError`      | Base exception for all fcmat errors               |
| `FCMatParseError` | Raised on malformed input; has a `line` attribute |

## FCMat File Format

FCMat files are a strict subset of YAML used by FreeCAD to define material properties. Key characteristics:

- UTF-8 encoding, optionally with a BOM
- Document starts with `---`
- Comments begin with `#`
- Sections and keys use 2-space indentation per level
- All leaf values are double-quoted strings

Example file:

```yaml
---
# File created by FreeCAD 1.0.2 Revision: 39319 (Git)
General:
  UUID: "1d8534f9-83cf-4524-be9a-e37eed281f76"
  Name: "Aluminum"
  Author: "David Carter"
  License: "GPL-2.0-or-later"
AppearanceModels:
  Basic Rendering:
    UUID: "f006c7e4-35b7-43d5-bbf9-c5d572309e6e"
    Shininess: "0.09"
    Transparency: "0"
```

## Requirements

- Python 3.11 or later

## License

This project is dual-licensed under the
[MIT License](LICENSES/MIT.md)
and the
[Apache License 2.0](LICENSES/Apache-2.0.md). You may choose either license.

`SPDX-License-Identifier: MIT OR Apache-2.0`
