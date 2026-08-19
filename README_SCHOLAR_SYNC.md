# Scholar + GitHub automatic sync (without ScrapingBee)

This package replaces ScrapingBee with `scholarly` and keeps the Google Scholar traffic deliberately small.

## Scholar workflow

1. Fetch profile metrics plus the 20 most recent publications (`sortby="year"`).
2. Wait a random 90-180 seconds by default.
3. Fetch the 20 most cited publications (`sortby="citedby"`).
4. Never call `scholarly.fill(pub)` on an individual publication.

The delay can be changed through `SCHOLAR_DELAY_MIN` and `SCHOLAR_DELAY_MAX` in the workflow.

Google Scholar has no official public API for this use and may still rate-limit or block automated requests. The script therefore preserves the previous JSON values whenever one of the Scholar phases fails instead of replacing them with zeros or empty arrays.

## Output JSON

`data/scholar_github.json` contains:

- `metrics`
- `scholar_profile`
- `publications` (backward-compatible alias for recent publications)
- `publications_recent`
- `publications_top_cited`
- `repositories`
- `sync_status`

## GitHub Actions

Replace your current workflow with `.github/workflows/update-data.yml`.

The ScrapingBee secret is no longer used and can be deleted from the repository settings after the new workflow has been tested successfully.
