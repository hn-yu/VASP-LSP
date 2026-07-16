# Changelog

All notable changes to the VASP-LSP project will be documented in this file.

## [0.4.5] - 2026-07-16

### Added
- Tag-only PyPI trusted-publishing workflow using GitHub OIDC and the protected `pypi` environment
- Fresh-wheel release smoke covering the server, agent CLI, and valid, invalid, and runtime-log fixtures

### Changed
- Aligned Python, VS Code, VERSION, and OpenQC capability metadata for the 0.4.5 release

## [0.4.4] - 2026-06-15

### Added
- VERSION file for release version discoverability
- Release provenance metadata in lsp-capabilities.json

### Changed
- Aligned version across pyproject.toml, VERSION, and CHANGELOG

## [0.4.3] - 2026-03-04

### Added
- Implemented POSCAR file quick fixes
- Implemented KPOINTS file quick fixes
- Added comprehensive documentation

### Tests
- Total tests: 450
- Coverage maintained at 100%

## [0.4.2] - 2026-03-04

### Added
- Implemented POSCAR file diagnostics
- Implemented KPOINTS file diagnostics

### Tests
- Total tests: 428
- Coverage maintained at 100%

## [0.4.1] - 2026-03-04

### Fixed
- Fixed all Ruff lint errors
- Fixed 461 lint errors across 40 files

### Tests
- 416 tests passing with 100% coverage

## [0.4.0] - 2026-03-03

### Added
- VSCode extension configuration
- Syntax highlighting for all file types

## [0.3.0] - 2026-03-01

### Added
- Document formatting support
- Quick fixes for common INCAR issues

## [0.2.0] - 2026-02-28

### Added
- LSP server implementation
- Completion provider
- Hover documentation
- Diagnostics for INCAR files

## [0.1.0] - 2026-02-25

### Added
- Initial release
- INCAR, POSCAR, KPOINTS parsers
- Basic LSP server structure
