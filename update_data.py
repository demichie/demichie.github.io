import json
import os
import re
import sys
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE ---
GITHUB_USERNAME = 'demichie'
SCHOLAR_ID = '6ev_1zUAAAAJ'
OUTPUT_FILE = 'data/scholar_github.json'

# Recupero della chiave API dai Repository Secrets / Variabili d'ambiente
SCRAPINGBEE_API_KEY = os.environ.get('SCRAPINGBEE_KEY')

def get_scholar_data_via_scrapingbee():
    print(f"Fetching Google Scholar data via ScrapingBee for ID: {SCHOLAR_ID}...")
    
    # URL del profilo Scholar ordinato per data di pubblicazione
    target_url = f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en&view_op=list_short&sortby=pubdate"
    
    params = {
        'api_key': SCRAPINGBEE_API_KEY,
        'url': target_url,
        'custom_google': 'true'  # Parametro fondamentale per bypassare le protezioni Google
    }
    
    try:
        response = requests.get('https://app.scrapingbee.com/api/v1/', params=params, timeout=30)
        
        if response.status_code != 200:
            print(f"ScrapingBee returned error status code: {response.status_code}")
            return None, None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        html_text = response.text
        
        # 1. Estrazione metriche (Citations, h-index, i10-index)
        citations_match = re.search(r'Citations<\/a><\/td><td class="gsc_rsb_std">(\d+)<\/td>', html_text)
        hindex_match = re.search(r'h-index<\/a><\/td><td class="gsc_rsb_std">(\d+)<\/td>', html_text)
        i10index_match = re.search(r'i10-index<\/a><\/td><td class="gsc_rsb_std">(\d+)<\/td>', html_text)
        
        metrics = {
            "total_citations": int(citations_match.group(1)) if citations_match else 0,
            "h_index": int(hindex_match.group(1)) if hindex_match else 0,
            "i10_index": int(i10index_match.group(1)) if i10index_match else 0
        }
        
        # 2. Estrazione pubblicazioni
        publications = []
        rows = soup.select('.gsc_a_tr')
        
        print(f"Found {len(rows)} publications on Scholar page.")
        
        for row in rows:
            title_el = row.select_one('.gsc_a_at')
            if not title_el:
                continue
            title = title_el.text.strip()
            
            details = row.select('.gs_gray')
            authors = details[0].text.strip() if len(details) > 0 else ""
            journal = details[1].text.strip() if len(details) > 1 else "Scientific Publication"
            
            year_el = row.select_one('.gsc_a_y')
            year = year_el.text.strip() if year_el else ""
            
            citations_el = row.select_one('.gsc_a_ac')
            try:
                pub_citations = int(citations_el.text.strip()) if citations_el and citations_el.text.strip() else 0
            except ValueError:
                pub_citations = 0
                
            publications.append({
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
                "citations": pub_citations
            })
            
        print(f"Successfully retrieved {len(publications)} publications and updated metrics (Citations: {metrics['total_citations']}, h-index: {metrics['h_index']}).")
        return metrics, publications

    except Exception as e:
        print(f"Error during ScrapingBee execution: {e}")
        return None, None

def get_github_data():
    print(f"Fetching GitHub repositories for user: {GITHUB_USERNAME}...")
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/repos?sort=pushed&per_page=100"
    
    headers = {"Accept": "application/vnd.github.v3+json"}
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
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
                        "language": repo.get('language', 'Code')
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
    
    # Check di sicurezza per la chiave API
    if not SCRAPINGBEE_API_KEY:
        print("Error: SCRAPINGBEE_KEY environment variable is missing!")
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    scholar_metrics, publications = get_scholar_data_via_scrapingbee()
    github_repos = get_github_data()

    output_data = {
        "last_updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "metrics": scholar_metrics if scholar_metrics else {"total_citations": 0, "h_index": 0, "i10_index": 0},
        "publications": publications if publications else [],
        "repositories": github_repos if github_repos else []
    }

    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Successfully generated {OUTPUT_FILE} with ScrapingBee + GitHub data!")
    except Exception as e:
        print(f"Critical Error writing to {OUTPUT_FILE}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()