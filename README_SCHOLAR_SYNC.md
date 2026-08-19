# Scholar + GitHub sync without ScrapingBee — v2

This version is designed for the situation observed on GitHub-hosted Actions runners: direct Google Scholar access may be blocked even when only an author profile is requested.

## Retrieval strategy

For each Scholar phase:

1. Try the current connection (initially direct).
2. If it fails, configure a fresh `scholarly.ProxyGenerator().FreeProxies()` connection and retry once.
3. Never call `scholarly.fill(pub)` on individual publication pages.
4. Preserve the previous JSON data when both attempts fail.

There are two Scholar phases, separated by a random 90–180 second delay:

- metrics + 20 most recent publications (`sortby="year"`)
- 20 most cited publications (`sortby="citedby"`)

Free public proxies are inherently less reliable than a paid proxy/API. They are used only as a fallback and only for public Scholar requests. The GitHub token is used separately for `api.github.com` and is never passed to the Scholar proxy.

## Better freshness metadata

`last_updated` means only "the workflow ran at this time".

The JSON now also stores:

- `scholar_recent_last_successful_update`
- `scholar_top_cited_last_successful_update`
- `github_last_successful_update`

and detailed `sync_status` fields including connection source and error text. This prevents a failed Scholar refresh from looking like fresh Scholar data.

## What to look for after workflow_dispatch

A successful run should produce something similar to:

```json
"sync_status": {
  "scholar_recent_ok": true,
  "scholar_recent_source": "direct" or "free_proxy",
  "scholar_top_cited_ok": true,
  "scholar_top_cited_source": "direct" or "free_proxy",
  "github_ok": true
}
```

If Scholar still fails, the JSON will now contain the actual exception class/message in `scholar_recent_error` and `scholar_top_cited_error`.
