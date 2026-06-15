# VASP official documentation assets

Captured upstream anchors for the docs → wiki → rules pipeline. Large VASP
manual pages stay linked upstream; this directory stores stable indexes,
checksums, and refresh metadata.

## Refresh

```bash
python scripts/wiki_lint.py
vasp-lsp-tool rules --format json > /dev/null
```

After editing wiki pages or `rules/diagnostics.yaml`, run the lint script so
provenance links and fixture paths stay aligned with `lsp-capabilities.json`.

## Manifest

See `asset-manifest.json` for retrieval dates, URLs, checksums, and license notes.
