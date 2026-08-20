# Scholar/GitHub sync v3 — publication links

This package keeps the v2 Scholar workflow and adds publication-link discovery **without opening individual Google Scholar publication pages**.

## What v3 adds

For the union of the 20 most recent and 20 most-cited Scholar entries, `update_data.py` tries to attach a reliable publication URL:

1. **Crossref** — searches bibliographic metadata and accepts only high-confidence matches; saves a canonical `https://doi.org/...` URL.
2. **arXiv** — if Crossref does not match and the Scholar venue already contains an explicit arXiv identifier, constructs the arXiv URL directly.
3. **OpenAlex (optional)** — used only when `OPENALEX_API_KEY` is configured.

Each publication can gain these fields:

```json
{
  "doi": "10.1016/j.softx.2026.102785",
  "url": "https://doi.org/10.1016/j.softx.2026.102785",
  "link_source": "crossref",
  "link_match_score": 1.0
}
```

If a reliable match is not found, `url` remains empty. The script intentionally prefers missing links over false links.

## Efficient weekly operation

- The recent and most-cited lists are deduplicated before link lookup.
- URLs already stored in the previous `data/scholar_github.json` are reused, so unchanged publications do not generate new Crossref/OpenAlex searches every week.
- Crossref requests are separated by `LINK_LOOKUP_DELAY` (default 0.35 s).
- Crossref requires no API key.

## Optional Crossref polite-pool setting

Crossref works without registration. Optionally create a GitHub **Repository variable** named:

`CROSSREF_MAILTO`

with an email address. The workflow already reads it. This identifies the client to Crossref and enables their polite-pool behavior.

## Optional OpenAlex fallback

In 2026 OpenAlex requires an API key for normal API usage. Crossref + explicit arXiv detection work without it.

If you want the additional OpenAlex fallback:

1. Create a free OpenAlex API key.
2. Add it as repository secret `OPENALEX_API_KEY`.
3. Run the workflow again.

If the secret is absent, the script simply skips OpenAlex.

## Files to replace

- `update_data.py`
- `requirements.txt`
- `.github/workflows/update-data.yml`
- `index.html`

The v3 `index.html` reads both `publications_recent` and `publications_top_cited`, provides **Most recent / Most cited** buttons, and makes a publication title clickable only when the JSON contains a safe HTTP(S) `url`.

## Expected JSON diagnostics

The generated JSON includes:

```json
"link_enrichment": {
  "unique_publications": 31,
  "cached_links_reused": 22,
  "lookups_attempted": 9,
  "new_links_found": 7,
  "unresolved": 2,
  "openalex_enabled": false
}
```

and `sync_status.publication_links_ok` indicates whether the overall enrichment phase completed without an unexpected exception. Individual unresolved publications are normal and do not make the phase fail.
