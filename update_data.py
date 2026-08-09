import json
import requests
import sys
import re
import time

# --- CONFIGURATION ---
GITHUB_USERNAME = 'demichie'
SCHOLAR_ID = '6ev_1zUAAAAJ'

def get_scholar_data():
    print(f"Fetching Google Scholar data for ID: {SCHOLAR_ID}...")
    # Ordiniamo la pagina per data (view_op=list_short&sortby=pubdate) per prendere gli ultimi paper
    url = f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en&view_op=list_short&sortby=pubdate"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Scholar page returned status code: {response.status_code}")
            return None, None
            
        html = response.text
        
        # 1. PARSING METRICHE BASE
        citations_match = re.search(r'Citations<\/a><\/td><td class="gsc_rsb_std">(\d+)<\/td>', html)
        hindex_match = re.search(r'h-index<\/a><\/td><td class="gsc_rsb_std">(\d+)<\/td>', html)
        i10index_match = re.search(r'i10-index<\/a><\/td><td class="gsc_rsb_std">(\d+)<\/td>', html)
        
        metrics = {
            "id": SCHOLAR_ID,
            "citations": int(citations_match.group(1)) if citations_match else 0,
            "hindex": int(hindex_match.group(1)) if hindex_match else 0,
            "i10index": int(i10index_match.group(1)) if i10index_match else 0
        }
        
        # 2. PARSING PUBBLICAZIONI RECENTI (Dalla tabella principale)
        # Cerchiamo i blocchi delle righe delle pubblicazioni
        pub_rows = re.findall(r'<tr class="gsc_a_tr">(.+?)<\/tr>', html, re.DOTALL)
        publications = []
        
        print(f"Found {len(pub_rows)} publications on the first page. Parsing...")
        
        for row in pub_rows:
            # Estrazione Titolo e Link
            title_match = re.search(r'<a href="([^"]+)" class="gsc_a_at">([^<]+)<\/a>', row)
            if not title_match:
                continue
            title = title_match.group(2)
            
            # Estrazione Dettagli (Autori e Rivista/Convegno)
            details = re.findall(r'<div class="gs_gray">([^<]+)<\/div>', row)
            venue = details[1] if len(details) > 1 else "Unknown Venue"
            
            # Estrazione Citazioni della singola opera
            pub_citations_match = re.search(r'<a href="[^"]+" class="gsc_a_ac gs_ibl">(\d+)<\/a>', row)
            pub_citations = int(pub_citations_match.group(1)) if pub_citations_match else 0
            
            # Estrazione Anno
            year_match = re.search(r'<span class="gsc_a_h gsc_a_hc gs_ibl">(\d+)<\/span>', row)
            year = year_match.group(1) if year_match else "N/A"
            
            # Logica di categorizzazione automatica basata su parole chiave nella venue
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
                "citations": pub_citations,
                "type": pub_type
            })
            
        return metrics, publications
        
    except Exception as e:
        print(f"Error parsing Scholar data: {e}")
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
    
    # 1. Leggi il file data.json esistente per preservare didattica e progetti
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            current_data = json.load(f)
        print("Existing data.json loaded successfully.")
    except Exception as e:
        print(f"Error reading data.json: {e}")
        sys.exit(1)

    # 2. Recupera i dati freschi da Scholar
    scholar_metrics, publications = get_scholar_data()
    
    # Inseriamo una pausa di 5 secondi per cortesia tra le chiamate ai due provider diversi
    time.sleep(5)
    
    # 3. Recupera i dati da GitHub
    github_repos = get_github_data()

    # 4. Aggiorna le sezioni se il recupero ha avuto successo
    if scholar_metrics is not None:
        current_data['scholar'] = scholar_metrics
    if publications is not None and len(publications) > 0:
        current_data['publications'] = publications
    if github_repos is not None:
        current_data['github_repos'] = github_repos

    # 5. Salva il file data.json aggiornato
    try:
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
        print("data.json successfully updated with fresh metrics, publications, and repositories!")
    except Exception as e:
        print(f"Critical Error writing to data.json: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()