import json
import requests
from scholarly import scholarly

# --- CONFIGURATION ---
SCHOLAR_ID = '6ev_1zUAAAAJ'
GITHUB_USERNAME = 'demichie'

def get_scholar_data():
    print("Fetching Google Scholar data...")
    try:
        author = scholarly.search_author_id(SCHOLAR_ID)
        author_info = scholarly.fill(author, sections=['basics', 'indices', 'publications'])
        
        scholar_metrics = {
            "citations": author_info.get('citedby', 0),
            "hindex": author_info.get('hindex', 0),
            "i10index": author_info.get('i10index', 0)
        }
        
        publications = []
        # Prende le pubblicazioni (puoi aumentare il limite se necessario)
        for pub in author_info.get('publications', [])[:30]:
            try:
                fill_pub = scholarly.fill(pub)
                bib = fill_pub.get('bib', {})
                
                # Logica elementare per suddividere le categorie basandosi sulle parole chiave
                venue = bib.get('journal', bib.get('conference', bib.get('publisher', ''))).lower()
                pub_type = 'paper' # Default
                
                if 'chapter' in venue or 'capitolo' in venue:
                    pub_type = 'chapter'
                elif 'book' in venue or 'libro' in venue:
                    pub_type = 'book'
                
                publications.append({
                    "title": bib.get('title', 'Unknown Title'),
                    "year": bib.get('pub_year', 'N/A'),
                    "venue": bib.get('journal', bib.get('conference', bib.get('publisher', ''))),
                    "citations": fill_pub.get('num_citations', 0),
                    "type": pub_type
                })
            except Exception as e:
                print(f"Skipping a publication due to error: {e}")
                
        return scholar_metrics, publications
    except Exception as e:
        print(f"Error fetching Scholar data: {e}")
        return None, None

def get_github_data():
    print("Fetching GitHub repositories...")
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/repos?sort=pushed&per_page=6"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            repos = response.json()
            github_repos = []
            for repo in repos:
                # Escludiamo i fork e la repository del sito stesso
                if not repo['fork'] and repo['name'] != f"{GITHUB_USERNAME}.github.io":
                    github_repos.append({
                        "name": repo['name'],
                        "description": repo['description'],
                        "url": repo['html_url'],
                        "stars": repo['stargazers_count'],
                        "language": repo['language'],
                        "updated_at": repo['pushed_at'][:10] # Prende solo la data YYYY-MM-DD
                    })
            return github_repos
        else:
            print(f"GitHub API error: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error fetching GitHub data: {e}")
        return None

def main():
    # 1. Leggi il file data.json esistente per preservare didattica e progetti
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            current_data = json.load(f)
    except Exception:
        current_data = {"teaching": [], "projects": []}

    # 2. Recupera i nuovi dati automatici
    scholar_metrics, publications = get_scholar_data()
    github_repos = get_github_data()

    # 3. Aggiorna solo le sezioni automatiche se il recupero ha avuto successo
    if scholar_metrics:
        current_data['scholar'] = scholar_metrics
    if publications:
        current_data['publications'] = publications
    if github_repos:
        current_data['github_repos'] = github_repos

    # 4. Salva il file data.json aggiornato
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(current_data, f, indent=2, ensure_ascii=False)
    print("data.json updated successfully!")

if __name__ == "__main__":
    main()