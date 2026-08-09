import json
import requests
import sys
import time
import random
from scholarly import scholarly

# --- CONFIGURAZIONE ---
GITHUB_USERNAME = 'demichie'
SCHOLAR_ID = '6ev_1zUAAAAJ'

def get_scholar_data():
    print(f"Fetching Google Scholar data using scholarly for ID: {SCHOLAR_ID}...")
    try:
        # 1. Cerca l'autore tramite ID
        author = scholarly.search_author_id(SCHOLAR_ID)
        
        # Controllo di sicurezza fondamentale: se scholarly viene bloccato a monte, restituisce None
        if author is None:
            print("Warning: Google Scholar returned None (likely a bot block or CAPTCHA). Skipping Scholar update to preserve existing data.")
            return None, None
            
        # 2. Compila solo le sezioni base, indici e la lista delle pubblicazioni
        print("Author found. Filling profile sections...")
        filled_author = scholarly.fill(author, sections=['basics', 'indices', 'publications'])
        
        if filled_author is None:
            print("Warning: Failed to fill author sections. Skipping Scholar update.")
            return None, None

        # 3. Estrazione indici bibliometrici principali
        metrics = {
            "id": SCHOLAR_ID,
            "citations": filled_author.get('citedby', 0),
            "hindex": filled_author.get('hindex', 0),
            "i10index": filled_author.get('i10index', 0)
        }
        
        # 4. Estrazione e ordinamento pubblicazioni
        raw_pubs = filled_author.get('publications', [])
        if not raw_pubs:
            print("No publications found or unable to retrieve the list.")
            return metrics, None

        print(f"Found {len(raw_pubs)} total publications. Sorting and selecting top 20 recent...")
        
        # Funzione helper per estrarre l'anno di pubblicazione in modo sicuro
        def extract_year(pub):
            try:
                return int(pub.get('bib', {}).get('pub_year', 0))
            except (ValueError, TypeError):
                return 0

        # Ordina le pubblicazioni per anno decrescente (le più recenti in alto)
        raw_pubs.sort(key=extract_year, reverse=True)
        
        # Seleziona solo le prime 20 pubblicazioni
        recent_pubs = raw_pubs[:20]
        
        publications = []
        for pub in recent_pubs:
            bib = pub.get('bib', {})
            title = bib.get('title', 'Untitled')
            year = str(bib.get('pub_year', 'N/A'))
            venue = bib.get('journal') or bib.get('venue') or 'Scientific Publication'
            num_citations = pub.get('num_citations', 0)
            
            # Categorizzazione basata su parole chiave nella venue
            v_low = venue.lower()
            pub_type = 'paper'
            if 'chapter' in v_low or 'capitolo' in v_low:
                pub_type = 'chapter'
            elif 'book' in v_low or 'libro' in v_low or 'monograph' in v_low:
                pub_type = 'book'

            publications.append({
                "title": title,
                "year": year,
                "venue": venue,
                "citations": num_citations,
                "type": pub_type
            })

        print(f"Successfully processed {len(publications)} publications and updated metrics (Citations: {metrics['citations']}, h-index: {metrics['hindex']}).")
        return metrics, publications

    except Exception as e:
        print(f"Error fetching data with scholarly: {e}")
        return None, None

def get_github_data():
    print(f"Fetching GitHub repositories for user: {GITHUB_USERNAME}...")
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/repos?sort=pushed&per_page=10"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            repos = response.json()
            github_repos = []
            for repo in repos:
                if not repo.get('fork', False) and repo.get('name') != f"{GITHUB_USERNAME}.github.io":
                    github_repos.append({
                        "name": repo.get('name', 'Unknown'),
                        "description": repo.get('description', 'No description provided.'),
                        "url": repo.get('html_url', '#'),
                        "stars": repo.get('stargazers_count', 0),
                        "language": repo.get('language', 'Code'),
                        "updated_at": repo.get('pushed_at', 'Recently')[:10]
                    })
            return github_repos
        else:
            print(f"GitHub API returned status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error connecting to GitHub API: {e}")
        return None

def main():
    print("Starting automated data sync...")
    
    # 1. Carica il data.json esistente per preservare i dati in caso di errore di Scholar
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            current_data = json.load(f)
        print("Existing data.json loaded successfully.")
    except Exception as e:
        print(f"Error reading data.json: {e}")
        sys.exit(1)

    # 2. Recupera i dati da Scholar tramite scholarly
    scholar_metrics, publications = get_scholar_data()
    
    # Pausa precauzionale prima di chiamare l'API di GitHub
    time.sleep(random.uniform(2.0, 4.0))
    
    # 3. Recupera i dati da GitHub
    github_repos = get_github_data()

    # 4. Aggiorna data.json SOLO se i rispettivi recuperi hanno avuto successo
    # Se Scholar ha fallito (None), la vecchia lista dei paper rimane intatta nel JSON!
    if scholar_metrics is not None:
        current_data['scholar'] = scholar_metrics
    if publications is not None and len(publications) > 0:
        current_data['publications'] = publications
    if github_repos is not None:
        current_data['github_repos'] = github_repos

    # 5. Salva il file data.json
    try:
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
        print("data.json successfully processed!")
    except Exception as e:
        print(f"Critical Error writing to data.json: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()