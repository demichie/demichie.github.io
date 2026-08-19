import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests
from scholarly import scholarly

# --- CONFIGURAZIONE ---
GITHUB_USERNAME = "demichie"
SCHOLAR_ID = "6ev_1zUAAAAJ"
OUTPUT_FILE = "data/scholar_github.json"
PUBLICATION_LIMIT = 20

# Pausa casuale tra le due fasi Scholar. I valori possono essere sovrascritti
# come variabili d'ambiente nel workflow, senza modificare questo file.
SCHOLAR_DELAY_MIN = int(os.environ.get("SCHOLAR_DELAY_MIN", "90"))
SCHOLAR_DELAY_MAX = int(os.environ.get("SCHOLAR_DELAY_MAX", "180"))

# Limita i retry automatici di scholarly: se Google blocca il runner e' meglio
# conservare i dati precedenti che generare molte richieste ravvicinate.
scholarly.set_retries(1)
scholarly.set_timeout(30)


def load_existing_output():
    """Carica il JSON esistente per usarlo come fallback in caso di blocco."""
    if not os.path.exists(OUTPUT_FILE):
        return {}

    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"Warning: could not read existing {OUTPUT_FILE}: {exc}")
        return {}


def extract_publications(publications):
    """Converte le entry 'light' del profilo Scholar nel formato del sito.

    Importante: qui NON viene mai chiamato scholarly.fill(pub), quindi non si
    aprono le pagine delle singole pubblicazioni.
    """
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

        result.append(
            {
                "title": str(bib.get("title", "")).strip(),
                "authors": str(authors or "").strip(),
                "journal": str(venue).strip(),
                "year": str(bib.get("pub_year", "") or "").strip(),
                "citations": int(pub.get("num_citations", 0) or 0),
            }
        )

    return result


def get_scholar_recent_and_metrics():
    """Recupera metriche e le 20 pubblicazioni piu' recenti."""
    print(
        f"Fetching Scholar metrics and {PUBLICATION_LIMIT} most recent publications "
        f"for ID: {SCHOLAR_ID}..."
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
    print(
        f"Scholar recent phase completed: {len(publications)} publications, "
        f"{metrics['total_citations']} citations, h-index {metrics['h_index']}."
    )
    return metrics, profile, publications


def get_scholar_top_cited():
    """Recupera le 20 pubblicazioni piu' citate, senza riempire i singoli paper."""
    print(
        f"Fetching {PUBLICATION_LIMIT} most cited Scholar publications "
        f"for ID: {SCHOLAR_ID}..."
    )

    # Oggetto autore nuovo: evita che la sezione publications gia' riempita con
    # sortby='year' venga riutilizzata invece di essere riletta con 'citedby'.
    author = scholarly.search_author_id(SCHOLAR_ID)
    author = scholarly.fill(
        author,
        sections=["publications"],
        sortby="citedby",
        publication_limit=PUBLICATION_LIMIT,
    )

    publications = extract_publications(author.get("publications", []))
    print(f"Scholar cited-by phase completed: {len(publications)} publications.")
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
        return github_repos
    except Exception as exc:
        print(f"Error connecting to GitHub API: {exc}")
        return None


def main():
    print("Starting automated Scholar + GitHub data sync (no ScrapingBee)...")

    if SCHOLAR_DELAY_MIN < 0 or SCHOLAR_DELAY_MAX < SCHOLAR_DELAY_MIN:
        print("Invalid SCHOLAR_DELAY_MIN/SCHOLAR_DELAY_MAX configuration.")
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    previous = load_existing_output()

    metrics = None
    profile = None
    recent_publications = None
    top_cited_publications = None

    # Fase Scholar 1: metriche + recenti.
    try:
        metrics, profile, recent_publications = get_scholar_recent_and_metrics()
    except Exception as exc:
        print(f"Scholar recent/metrics phase failed: {exc}")
        print("Previous Scholar metrics/recent publications will be preserved if available.")

    # Pausa SEMPRE tra le due fasi Scholar, anche se la prima e' fallita.
    delay = random.uniform(SCHOLAR_DELAY_MIN, SCHOLAR_DELAY_MAX)
    print(f"Waiting {delay:.0f} seconds before the second Scholar phase...")
    time.sleep(delay)

    # Fase Scholar 2: piu' citate.
    try:
        top_cited_publications = get_scholar_top_cited()
    except Exception as exc:
        print(f"Scholar top-cited phase failed: {exc}")
        print("Previous top-cited publications will be preserved if available.")

    github_repos = get_github_data()

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

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    output_data = {
        "last_updated": now_utc,
        "scholar_profile": final_profile,
        "metrics": final_metrics,
        # Compatibilita' con la versione precedente di index.html:
        # 'publications' continua a significare le 20 piu' recenti.
        "publications": final_recent,
        "publications_recent": final_recent,
        "publications_top_cited": final_top,
        "repositories": final_repos,
        "sync_status": {
            "scholar_recent_ok": recent_publications is not None,
            "scholar_top_cited_ok": top_cited_publications is not None,
            "github_ok": github_repos is not None,
        },
    }

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Successfully generated {OUTPUT_FILE} without ScrapingBee.")
    except Exception as exc:
        print(f"Critical error writing {OUTPUT_FILE}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
