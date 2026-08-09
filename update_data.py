import json
import requests
import sys

# --- CONFIGURAZIONE ---
GITHUB_USERNAME = 'demichie'
AUTHOR_NAME = "Mattia de' Michieli Vitturi"

def get_academic_data():
    print(f"Fetching academic publications for: {AUTHOR_NAME}...")
    # Interroghiamo l'API di Semantic Scholar
    search_url = f"https://api.semanticscholar.org/graph/v1/author/search?query={AUTHOR_NAME}&fields=name,citationCount,hIndex,papers.title,papers.year,papers.venue,papers.citationCount"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    
    try:
        response = requests.get(search_url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get('data') and len(data['data']) > 0:
                author_data = data['data'][0] # Prende il profilo autore corrispondente
                
                metrics = {
                    "id": "6ev_1zUAAAAJ",
                    "citations": author_data.get('citationCount', 0),
                    "hindex": author_data.get('hIndex', 0),
                    "i10index": 0
                }
                
                raw_papers = author_data.get('papers', [])
                
                # Ordina i paper dal più recente al meno recente
                raw_papers.sort(key=lambda x: x.get('year') or 0, reverse=True)
                
                publications = []
                for p in raw_papers[:25]: # Prende le prime 25 pubblicazioni recenti
                    venue = p.get('venue') or ''
                    v_low = venue.lower()
                    
                    pub_type = 'paper'
                    if 'chapter' in v_low:
                        pub_type = 'chapter'
                    elif 'book' in v_low:
                        pub_type = 'book'
                        
                    publications.append({
                        "title": p.get('title', 'Untitled'),
                        "year": str(p.get('year', 'N/A')),
                        "venue": venue if venue else "Scientific Publication",
                        "citations": p.get('citationCount', 0),
                        "type": pub_type
                    })
                    
                print(f"Successfully retrieved {len(publications)} publications and {metrics['citations']} citations!")
                return metrics, publications
        print(f"Academic API returned status code: {response.status_code}")
        return None, None
    except Exception as e:
        print(f"Error fetching academic data: {e}")
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
    
    # 1. Carica il data.json per preservare Didattica e Progetti
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            current_data = json.load(f)
        print("Existing data.json loaded successfully.")
    except Exception as e:
        print(f"Error reading data.json: {e}")
        sys.exit(1)

    # 2. Recupera le pubblicazioni/metriche e i repository GitHub
    scholar_metrics, publications = get_academic_data()
    github_repos = get_github_data()

    # 3. Aggiorna data.json solo con le informazioni recuperate con successo
    if scholar_metrics is not None:
        current_data['scholar'] = scholar_metrics
    if publications is not None and len(publications) > 0:
        current_data['publications'] = publications
    if github_repos is not None:
        current_data['github_repos'] = github_repos

    # 4. Salva il file data.json
    try:
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
        print("data.json successfully updated with real publications and repositories!")
    except Exception as e:
        print(f"Critical Error writing to data.json: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()