# Contributing to freecad-material

:+1::tada: First off, thanks for taking the time to contribute! :tada::+1:

freecad-material aims to be a small, reliable, and dependency-free Python library.
Contributions that improve correctness, clarity, or maintainability are very welcome.

---

## Code of Conduct

Please note that this project has a [Contributor Covenant Code of Conduct]. By
participating in this project, you agree to abide by its terms. Instances of
abusive, harassing, or otherwise unacceptable behavior may be reported to the
project maintainer at:

* [mailto:mgcummings@yahoo.com?subject=CoC%20freecad-material](mailto:mgcummings@yahoo.com?subject=CoC%20freecad-material)

---

## What to contribute

Good candidates for contributions include:

* Bug fixes (especially compatibility issues with specific FreeCAD versions)
* Support for FCMat format variations or edge cases
* Documentation corrections or clarifications
* Performance or reliability improvements
* Tests for existing or fixed behavior

Please open an issue before starting large or opinionated changes.

---

## Style guidelines

### Python code

freecad-material is written in **pure Python** and targets **Python 3.11+**.

Please follow these guidelines:

* Follow [PEP 8] with a maximum line length of 99 characters
* Use type annotations on all public functions and methods
* Prefer simple, readable code over clever constructs
* Keep functions and methods small and focused
* Use `OrderedDict` subclassing patterns consistent with the existing `FCMat` class
* Do not introduce dependencies outside the Python standard library

If you add new public symbols:

* Add them to `__all__` in both `fcmat.py` and `__init__.py`
* Ensure they are documented with a docstring

---

### Documentation

* Keep documentation accurate to actual behavior
* Avoid suggesting unsupported or deprecated usage
* Prefer small, targeted changes over large rewrites
* Code examples should work when copied verbatim and tested against a real
  FreeCAD FCMat file

When changing only documentation, consider marking the commit accordingly (see
below).

---

## Git commit messages

Please follow these conventions:

* Use the **present tense** ("Add feature", not "Added feature")
* Use the **imperative mood** ("Fix bug", not "Fixes bug")
* Limit the first line to **72 characters or fewer**
* Reference related issues or pull requests when applicable
* Group related changes into a single logical commit

When only changing documentation, include `[ci skip]` in the commit title.

You may optionally prefix commits with a [gitmoji] if you find that helpful.

---

## Testing

Before submitting a pull request, ensure all tests pass:

```bash
uv run pytest
```

If you add new behavior, please add or update tests where practical. Tests live
in the `tests/` directory and should use real-world FCMat snippets where possible
to guard against FreeCAD compatibility regressions.

---

## Pull request process

1. Fork the repository
2. Create a topic branch from `main`
3. Make your changes with clear, focused commits
4. Ensure tests pass
5. Open a pull request with a clear description of the change

Small, focused pull requests are easier to review and more likely to be merged
quickly.

---

## Questions

If you are unsure about an approach or design decision, feel free to open an
issue to discuss it before writing code.

---

[Contributor Covenant Code of Conduct]: CODE_OF_CONDUCT.md
[PEP 8]: https://peps.python.org/pep-0008/
[gitmoji]: https://gitmoji.dev/
