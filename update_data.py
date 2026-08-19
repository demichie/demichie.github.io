import json
import os
import random
import sys
import time
import traceback
from datetime import datetime, timezone

import requests
from scholarly import ProxyGenerator, scholarly

# --- CONFIGURAZIONE ---
GITHUB_USERNAME = "demichie"
SCHOLAR_ID = "6ev_1zUAAAAJ"
OUTPUT_FILE = "data/scholar_github.json"
PUBLICATION_LIMIT = 20

SCHOLAR_DELAY_MIN = int(os.environ.get("SCHOLAR_DELAY_MIN", "90"))
SCHOLAR_DELAY_MAX = int(os.environ.get("SCHOLAR_DELAY_MAX", "180"))
USE_FREE_PROXY_FALLBACK = os.environ.get("SCHOLAR_FREE_PROXY_FALLBACK", "true").lower() in {
    "1", "true", "yes", "on"
}

# Keep scholarly conservative. A failed GitHub-hosted runner IP should not create
# a burst of retries against Google Scholar.
scholarly.set_retries(1)
scholarly.set_timeout(30)

# Tracks the connection currently configured inside scholarly.
_scholar_connection_source = "direct"


def utc_now_string():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load_existing_output():
    """Load the existing JSON so failed Scholar phases never erase good data."""
    if not os.path.exists(OUTPUT_FILE):
        return {}

    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"Warning: could not read existing {OUTPUT_FILE}: {exc}")
        return {}


def exception_text(exc):
    return f"{type(exc).__name__}: {exc}"


def configure_fresh_free_proxy():
    """Configure scholarly to use a newly selected public free proxy.

    This is only a fallback for public Google Scholar profile requests. No
    GitHub token or other secret is sent through this proxy.
    """
    global _scholar_connection_source

    print("Trying scholarly FreeProxies() fallback...")
    pg = ProxyGenerator()
    success = pg.FreeProxies()
    if not success:
        raise RuntimeError("ProxyGenerator.FreeProxies() could not find a working proxy")

    scholarly.use_proxy(pg)
    _scholar_connection_source = "free_proxy"
    print("A free proxy was configured successfully.")


def run_scholar_phase(label, func):
    """Run one Scholar phase, retrying once through a fresh free proxy."""
    global _scholar_connection_source

    first_source = _scholar_connection_source
    try:
        print(f"{label}: first attempt using {first_source} connection...")
        result = func()
        return result, first_source, None
    except Exception as first_exc:
        first_error = exception_text(first_exc)
        print(f"{label}: attempt via {first_source} failed: {first_error}")
        traceback.print_exc()

    if not USE_FREE_PROXY_FALLBACK:
        return None, first_source, first_error

    try:
        configure_fresh_free_proxy()
    except Exception as proxy_exc:
        proxy_error = exception_text(proxy_exc)
        print(f"{label}: free-proxy setup failed: {proxy_error}")
        traceback.print_exc()
        return None, "free_proxy_setup_failed", f"{first_error}; {proxy_error}"

    try:
        print(f"{label}: retrying through a fresh free proxy...")
        result = func()
        return result, "free_proxy", None
    except Exception as second_exc:
        second_error = exception_text(second_exc)
        print(f"{label}: free-proxy retry failed: {second_error}")
        traceback.print_exc()
        return None, "free_proxy", f"{first_error}; {second_error}"


def extract_publications(publications):
    """Convert light Scholar profile entries; never fill individual papers."""
    result = []

    for pub in publications[:PUBLICATION_LIMIT]:
        bib = pub.get("bib", {}) if isinstance(pub, dict) else {}
        authors = bib.get("author", "")
        if isinstance(authors, list):
            authors = ", ".join(str(a) for a in authors)

        venue = (
            bib.get("citation")
            or bib.get("journal")
            or bib.get("venue")
            or "Scientific Publication"
        )

        try:
            citations = int(pub.get("num_citations", 0) or 0)
        except (TypeError, ValueError):
            citations = 0

        result.append(
            {
                "title": str(bib.get("title", "")).strip(),
                "authors": str(authors or "").strip(),
                "journal": str(venue).strip(),
                "year": str(bib.get("pub_year", "") or "").strip(),
                "citations": citations,
            }
        )

    return result


def fetch_recent_metrics_profile():
    print(
        f"Fetching metrics and {PUBLICATION_LIMIT} most recent publications "
        f"for Scholar ID {SCHOLAR_ID}..."
    )

    author = scholarly.search_author_id(SCHOLAR_ID)
    author = scholarly.fill(
        author,
        sections=["basics", "indices", "counts", "publications"],
        sortby="year",
        publication_limit=PUBLICATION_LIMIT,
    )

    metrics = {
        "total_citations": int(author.get("citedby", 0) or 0),
        "h_index": int(author.get("hindex", 0) or 0),
        "i10_index": int(author.get("i10index", 0) or 0),
    }
    profile = {
        "name": author.get("name", ""),
        "affiliation": author.get("affiliation", ""),
        "interests": author.get("interests", []),
        "url_picture": author.get("url_picture", ""),
        "citations_per_year": author.get("cites_per_year", {}),
    }
    publications = extract_publications(author.get("publications", []))

    if not publications:
        raise RuntimeError("Scholar returned no recent publications")

    print(
        f"Recent Scholar phase succeeded: {len(publications)} publications, "
        f"{metrics['total_citations']} citations, h-index {metrics['h_index']}."
    )
    return metrics, profile, publications


def fetch_top_cited():
    print(
        f"Fetching {PUBLICATION_LIMIT} most cited publications for Scholar ID "
        f"{SCHOLAR_ID}..."
    )

    # New author object is essential: publications must be fetched again with
    # a different server-side sort order.
    author = scholarly.search_author_id(SCHOLAR_ID)
    author = scholarly.fill(
        author,
        sections=["publications"],
        sortby="citedby",
        publication_limit=PUBLICATION_LIMIT,
    )
    publications = extract_publications(author.get("publications", []))

    if not publications:
        raise RuntimeError("Scholar returned no most-cited publications")

    print(f"Most-cited Scholar phase succeeded: {len(publications)} publications.")
    return publications


def get_github_data():
    print(f"Fetching GitHub repositories for user: {GITHUB_USERNAME}...")
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/repos?sort=pushed&per_page=100"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        repos = response.json()

        github_repos = []
        for repo in repos:
            if repo.get("fork", False):
                continue
            if repo.get("name") == f"{GITHUB_USERNAME}.github.io":
                continue

            github_repos.append(
                {
                    "name": repo.get("name", "Unknown"),
                    "description": repo.get("description") or "No description provided.",
                    "url": repo.get("html_url", "#"),
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language") or "Code",
                }
            )

        print(f"GitHub phase completed: {len(github_repos)} repositories.")
        return github_repos, None
    except Exception as exc:
        error = exception_text(exc)
        print(f"GitHub phase failed: {error}")
        traceback.print_exc()
        return None, error


def main():
    print("Starting Scholar + GitHub data sync (no ScrapingBee)...")

    if SCHOLAR_DELAY_MIN < 0 or SCHOLAR_DELAY_MAX < SCHOLAR_DELAY_MIN:
        print("Invalid SCHOLAR_DELAY_MIN/SCHOLAR_DELAY_MAX configuration.")
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    previous = load_existing_output()

    # Scholar phase 1: metrics + recent publications.
    recent_result, recent_source, recent_error = run_scholar_phase(
        "Scholar recent/metrics", fetch_recent_metrics_profile
    )

    if recent_result is not None:
        metrics, profile, recent_publications = recent_result
    else:
        metrics = profile = recent_publications = None
        print("Preserving cached Scholar metrics/recent publications.")

    # Deliberate gap between the two sorted profile fetches.
    delay = random.uniform(SCHOLAR_DELAY_MIN, SCHOLAR_DELAY_MAX)
    print(f"Waiting {delay:.0f} seconds before the most-cited Scholar phase...")
    time.sleep(delay)

    top_cited_publications, top_source, top_error = run_scholar_phase(
        "Scholar most-cited", fetch_top_cited
    )
    if top_cited_publications is None:
        print("Preserving cached most-cited publications.")

    github_repos, github_error = get_github_data()

    previous_metrics = previous.get(
        "metrics", {"total_citations": 0, "h_index": 0, "i10_index": 0}
    )
    previous_recent = previous.get("publications_recent", previous.get("publications", []))
    previous_top = previous.get("publications_top_cited", [])
    previous_repos = previous.get("repositories", [])
    previous_profile = previous.get("scholar_profile", {})

    final_metrics = metrics if metrics is not None else previous_metrics
    final_profile = profile if profile is not None else previous_profile
    final_recent = recent_publications if recent_publications is not None else previous_recent
    final_top = top_cited_publications if top_cited_publications is not None else previous_top
    final_repos = github_repos if github_repos is not None else previous_repos

    now_utc = utc_now_string()

    previous_recent_success = previous.get("scholar_recent_last_successful_update")
    previous_top_success = previous.get("scholar_top_cited_last_successful_update")
    previous_github_success = previous.get("github_last_successful_update")

    recent_success_time = now_utc if recent_publications is not None else previous_recent_success
    top_success_time = now_utc if top_cited_publications is not None else previous_top_success
    github_success_time = now_utc if github_repos is not None else previous_github_success

    output_data = {
        # Overall workflow execution time. Do NOT interpret this as Scholar freshness.
        "last_updated": now_utc,
        "scholar_recent_last_successful_update": recent_success_time,
        "scholar_top_cited_last_successful_update": top_success_time,
        "github_last_successful_update": github_success_time,
        "scholar_profile": final_profile,
        "metrics": final_metrics,
        # Backward-compatible alias used by older index.html versions.
        "publications": final_recent,
        "publications_recent": final_recent,
        "publications_top_cited": final_top,
        "repositories": final_repos,
        "sync_status": {
            "scholar_recent_ok": recent_publications is not None,
            "scholar_recent_source": recent_source,
            "scholar_recent_error": recent_error,
            "scholar_top_cited_ok": top_cited_publications is not None,
            "scholar_top_cited_source": top_source,
            "scholar_top_cited_error": top_error,
            "github_ok": github_repos is not None,
            "github_error": github_error,
        },
    }

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Successfully generated {OUTPUT_FILE}.")
    except Exception as exc:
        print(f"Critical error writing {OUTPUT_FILE}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
