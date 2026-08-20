import json
import os
import random
import re
import sys
import time
import traceback
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher

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

# Link enrichment. Crossref works without an API key. CROSSREF_MAILTO is optional,
# but setting it as a repository variable is courteous and puts requests in the
# Crossref polite pool. OpenAlex is an optional fallback and requires a free API key.
CROSSREF_MAILTO = os.environ.get("CROSSREF_MAILTO", "").strip()
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()
LINK_LOOKUP_DELAY = float(os.environ.get("LINK_LOOKUP_DELAY", "0.35"))
CROSSREF_ROWS = int(os.environ.get("CROSSREF_ROWS", "5"))
CROSSREF_MIN_TITLE_SIMILARITY = float(os.environ.get("CROSSREF_MIN_TITLE_SIMILARITY", "0.88"))
CROSSREF_MIN_MATCH_SCORE = float(os.environ.get("CROSSREF_MIN_MATCH_SCORE", "0.92"))
OPENALEX_MIN_TITLE_SIMILARITY = float(os.environ.get("OPENALEX_MIN_TITLE_SIMILARITY", "0.90"))
OPENALEX_MIN_MATCH_SCORE = float(os.environ.get("OPENALEX_MIN_MATCH_SCORE", "0.93"))

HTTP_TIMEOUT = 25
USER_AGENT = "scholar-github-sync/3.0 (https://github.com/demichie)"

# Keep scholarly conservative. A failed GitHub-hosted runner IP should not create
# a burst of retries against Google Scholar.
scholarly.set_retries(1)
scholarly.set_timeout(30)

# Tracks the connection currently configured inside scholarly.
_scholar_connection_source = "direct"


def utc_now_string():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load_existing_output():
    """Load the existing JSON so failed phases never erase good data."""
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
    """Configure scholarly to use a newly selected public free proxy."""
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
    first_error = None
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


# -----------------------------------------------------------------------------
# Publication-link enrichment (NO Google Scholar requests below this point)
# -----------------------------------------------------------------------------

def normalize_text(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def publication_key(pub):
    return f"{normalize_text(pub.get('title'))}|{str(pub.get('year', '')).strip()}"


def title_similarity(a, b):
    na = normalize_text(a)
    nb = normalize_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def first_author_family(authors):
    text = str(authors or "").replace("…", "...").strip()
    if not text:
        return ""
    first = text.split(",", 1)[0].strip()
    tokens = normalize_text(first).split()
    return tokens[-1] if tokens else ""


def candidate_year_from_crossref(item):
    for field in ("published-print", "published-online", "issued", "created"):
        value = item.get(field)
        if not isinstance(value, dict):
            continue
        date_parts = value.get("date-parts")
        if date_parts and date_parts[0]:
            try:
                return int(date_parts[0][0])
            except (TypeError, ValueError, IndexError):
                pass
    return None


def candidate_year_from_openalex(item):
    try:
        value = item.get("publication_year")
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def score_candidate(pub, candidate_title, candidate_year=None, candidate_first_author=""):
    sim = title_similarity(pub.get("title"), candidate_title)
    score = sim

    pub_year = None
    try:
        if str(pub.get("year", "")).strip():
            pub_year = int(str(pub.get("year")).strip())
    except (TypeError, ValueError):
        pass

    if pub_year is not None and candidate_year is not None:
        delta = abs(pub_year - candidate_year)
        if delta == 0:
            score += 0.03
        elif delta == 1:
            score += 0.01
        elif delta >= 3:
            score -= 0.05

    expected_family = first_author_family(pub.get("authors"))
    candidate_family = first_author_family(candidate_first_author)
    if expected_family and candidate_family:
        if expected_family == candidate_family:
            score += 0.04
        elif expected_family not in candidate_family and candidate_family not in expected_family:
            score -= 0.02

    return min(1.0, max(0.0, score)), sim


def request_json(url, params, label):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    last_error = None

    for attempt in range(2):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
            if response.status_code == 429 and attempt == 0:
                retry_after = response.headers.get("Retry-After")
                try:
                    pause = min(30.0, max(2.0, float(retry_after))) if retry_after else 5.0
                except ValueError:
                    pause = 5.0
                print(f"{label}: rate limited; backing off for {pause:.0f}s...")
                time.sleep(pause)
                continue
            response.raise_for_status()
            return response.json(), None
        except Exception as exc:
            last_error = exception_text(exc)
            if attempt == 0:
                time.sleep(1.5)
            else:
                break

    return None, last_error


def crossref_lookup(pub):
    title = str(pub.get("title", "")).strip()
    if not title:
        return None, "missing title"

    query_parts = [title]
    first_author = str(pub.get("authors", "")).split(",", 1)[0].strip()
    year = str(pub.get("year", "")).strip()
    if first_author:
        query_parts.append(first_author)
    if year:
        query_parts.append(year)

    params = {
        "query.bibliographic": " ".join(query_parts),
        "rows": max(1, min(CROSSREF_ROWS, 10)),
    }
    if CROSSREF_MAILTO:
        params["mailto"] = CROSSREF_MAILTO

    data, error = request_json("https://api.crossref.org/works", params, "Crossref")
    if data is None:
        return None, error

    items = data.get("message", {}).get("items", [])
    best = None

    for item in items:
        titles = item.get("title") or []
        candidate_title = titles[0] if titles else ""
        authors = item.get("author") or []
        candidate_author = ""
        if authors:
            a = authors[0]
            candidate_author = " ".join(
                part for part in (a.get("given", ""), a.get("family", "")) if part
            )

        score, sim = score_candidate(
            pub,
            candidate_title,
            candidate_year_from_crossref(item),
            candidate_author,
        )
        if best is None or score > best[0]:
            best = (score, sim, item)

    if best is None:
        return None, "no Crossref candidates"

    score, sim, item = best
    doi = str(item.get("DOI", "")).strip()
    if not doi:
        return None, f"best Crossref candidate has no DOI (score={score:.3f})"

    if sim < CROSSREF_MIN_TITLE_SIMILARITY or score < CROSSREF_MIN_MATCH_SCORE:
        return None, f"Crossref match below threshold (title={sim:.3f}, score={score:.3f})"

    return {
        "doi": doi,
        "url": f"https://doi.org/{doi}",
        "link_source": "crossref",
        "link_match_score": round(score, 3),
    }, None


def arxiv_lookup(pub):
    haystack = " ".join(
        str(pub.get(field, "") or "") for field in ("title", "journal")
    )
    # Modern and legacy arXiv IDs. Prefer an explicit arXiv marker when present.
    patterns = [
        r"arxiv\s*[: ]\s*(\d{4}\.\d{4,5}(?:v\d+)?)",
        r"arxiv\s*[: ]\s*([a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, haystack, flags=re.IGNORECASE)
        if match:
            arxiv_id = match.group(1)
            return {
                "doi": "",
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "link_source": "arxiv",
                "link_match_score": 1.0,
            }, None
    return None, "no arXiv identifier in Scholar metadata"


def openalex_lookup(pub):
    if not OPENALEX_API_KEY:
        return None, "OPENALEX_API_KEY not configured"

    title = str(pub.get("title", "")).strip()
    if not title:
        return None, "missing title"

    params = {
        "search": f'"{title}"',
        "per_page": 5,
        "api_key": OPENALEX_API_KEY,
        "select": "id,display_name,publication_year,doi,primary_location,authorships",
    }

    data, error = request_json("https://api.openalex.org/works", params, "OpenAlex")
    if data is None:
        return None, error

    best = None
    for item in data.get("results", []):
        candidate_author = ""
        authorships = item.get("authorships") or []
        if authorships:
            candidate_author = (authorships[0].get("author") or {}).get("display_name", "")

        score, sim = score_candidate(
            pub,
            item.get("display_name", ""),
            candidate_year_from_openalex(item),
            candidate_author,
        )
        if best is None or score > best[0]:
            best = (score, sim, item)

    if best is None:
        return None, "no OpenAlex candidates"

    score, sim, item = best
    if sim < OPENALEX_MIN_TITLE_SIMILARITY or score < OPENALEX_MIN_MATCH_SCORE:
        return None, f"OpenAlex match below threshold (title={sim:.3f}, score={score:.3f})"

    doi_url = str(item.get("doi", "") or "").strip()
    doi = re.sub(r"^https?://doi\.org/", "", doi_url, flags=re.IGNORECASE)
    if doi:
        url = f"https://doi.org/{doi}"
    else:
        primary_location = item.get("primary_location") or {}
        url = str(primary_location.get("landing_page_url", "") or "").strip()
        if not url:
            url = str(item.get("id", "") or "").strip()

    if not url:
        return None, "OpenAlex candidate has no usable URL"

    return {
        "doi": doi,
        "url": url,
        "link_source": "openalex",
        "link_match_score": round(score, 3),
    }, None


def previous_link_cache(previous):
    cache = {}
    for field in ("publications_recent", "publications_top_cited", "publications"):
        for pub in previous.get(field, []) or []:
            if not isinstance(pub, dict) or not pub.get("url"):
                continue
            cache[publication_key(pub)] = {
                "doi": pub.get("doi", ""),
                "url": pub.get("url", ""),
                "link_source": pub.get("link_source", "cached"),
                "link_match_score": pub.get("link_match_score"),
            }
    return cache


def resolve_publication_link(pub):
    crossref_result, crossref_error = crossref_lookup(pub)
    if crossref_result:
        return crossref_result, None

    arxiv_result, arxiv_error = arxiv_lookup(pub)
    if arxiv_result:
        return arxiv_result, None

    openalex_result, openalex_error = openalex_lookup(pub)
    if openalex_result:
        return openalex_result, None

    errors = [
        f"Crossref: {crossref_error}",
        f"arXiv: {arxiv_error}",
        f"OpenAlex: {openalex_error}",
    ]
    return None, "; ".join(errors)


def enrich_publication_links(recent, top_cited, previous):
    """Add DOI/URL metadata while querying each unique publication at most once.

    Existing URLs from the previous JSON are reused, so unchanged publications do
    not generate new Crossref/OpenAlex calls every Monday.
    """
    cache = previous_link_cache(previous)
    resolved = dict(cache)
    lookup_errors = {}
    lookups_attempted = 0
    links_found = 0

    combined = []
    for pub in list(recent or []) + list(top_cited or []):
        if not isinstance(pub, dict) or not pub.get("title"):
            continue
        key = publication_key(pub)
        if key in {publication_key(p) for p in combined}:
            continue
        combined.append(pub)

    print(
        f"Link enrichment: {len(combined)} unique Scholar entries; "
        f"{len(cache)} cached links available."
    )

    for index, pub in enumerate(combined, start=1):
        key = publication_key(pub)
        if key in resolved and resolved[key].get("url"):
            print(f"Link {index}/{len(combined)}: cached: {pub.get('title', '')[:80]}")
            continue

        lookups_attempted += 1
        print(f"Link {index}/{len(combined)}: resolving: {pub.get('title', '')[:80]}")
        result, error = resolve_publication_link(pub)
        if result:
            resolved[key] = result
            links_found += 1
            print(f"  -> {result['link_source']}: {result['url']}")
        else:
            lookup_errors[key] = error
            print(f"  -> no reliable link: {error}")

        if LINK_LOOKUP_DELAY > 0:
            time.sleep(LINK_LOOKUP_DELAY)

    def apply(items):
        output = []
        for pub in items or []:
            enriched = dict(pub)
            link = resolved.get(publication_key(pub))
            if link and link.get("url"):
                enriched.update(link)
            else:
                # Explicit empty fields make the JSON schema predictable for the frontend.
                enriched.setdefault("doi", "")
                enriched.setdefault("url", "")
                enriched.setdefault("link_source", "")
                enriched.setdefault("link_match_score", None)
            output.append(enriched)
        return output

    stats = {
        "unique_publications": len(combined),
        "cached_links_reused": sum(1 for pub in combined if publication_key(pub) in cache),
        "lookups_attempted": lookups_attempted,
        "new_links_found": links_found,
        "unresolved": len(lookup_errors),
        "openalex_enabled": bool(OPENALEX_API_KEY),
    }
    return apply(recent), apply(top_cited), stats


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
    print("Starting Scholar + publication-link + GitHub data sync (no ScrapingBee)...")

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

    # Resolve URLs only after both Scholar lists are known. This phase does not use Scholar.
    try:
        final_recent, final_top, link_stats = enrich_publication_links(
            final_recent, final_top, previous
        )
        link_enrichment_error = None
    except Exception as exc:
        link_enrichment_error = exception_text(exc)
        print(f"Publication-link enrichment failed unexpectedly: {link_enrichment_error}")
        traceback.print_exc()
        link_stats = {
            "unique_publications": 0,
            "cached_links_reused": 0,
            "lookups_attempted": 0,
            "new_links_found": 0,
            "unresolved": 0,
            "openalex_enabled": bool(OPENALEX_API_KEY),
        }

    now_utc = utc_now_string()

    previous_recent_success = previous.get("scholar_recent_last_successful_update")
    previous_top_success = previous.get("scholar_top_cited_last_successful_update")
    previous_github_success = previous.get("github_last_successful_update")

    recent_success_time = now_utc if recent_publications is not None else previous_recent_success
    top_success_time = now_utc if top_cited_publications is not None else previous_top_success
    github_success_time = now_utc if github_repos is not None else previous_github_success

    output_data = {
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
        "link_enrichment": link_stats,
        "sync_status": {
            "scholar_recent_ok": recent_publications is not None,
            "scholar_recent_source": recent_source,
            "scholar_recent_error": recent_error,
            "scholar_top_cited_ok": top_cited_publications is not None,
            "scholar_top_cited_source": top_source,
            "scholar_top_cited_error": top_error,
            "publication_links_ok": link_enrichment_error is None,
            "publication_links_error": link_enrichment_error,
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
