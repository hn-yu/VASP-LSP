# Invalid VASP input fixtures

Canonical **invalid** fixtures referenced by `lsp-capabilities.json` → `fixturePaths.invalid`.

| Fixture | Expected rule | Severity |
|---------|---------------|----------|
| `blocking_invalid_tag.INCAR` | `vasp.incar.invalid_tag` | error (blocking) |
| `warning_missing_magmom.INCAR` | `vasp.spin.missing_magmom` | warning |

Per-rule goldens live under `tests/fixtures/rules/`.
