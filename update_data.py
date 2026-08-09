import json
import os
import re
import sys
import requests
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE ---
GITHUB_USERNAME = 'demichie'
SCHOLAR_ID = '6ev_1zUAAAAJ'

# Recupero della chiave API dai Repository Secrets / Variabili d'ambiente
SCRAPINGBEE_API_KEY = os.environ.get('SCRAPINGBEE_KEY')

def get_scholar_data_via_scrapingbee():
    print(f"Fetching Google Scholar data via ScrapingBee for ID: {SCHOLAR_ID}...")
    
    # URL del profilo Scholar ordinato per data di pubblicazione
    target_url = f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en&view_op=list_short&sortby=pubdate"
    
    params = {
        'api_key': SCRAPINGBEE_API_KEY,
        'url': target_url,
        'custom_google': 'true'  # Parametro fondamentale di ScrapingBee per bypassare le protezioni Google
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
            "id": SCHOLAR_ID,
            "citations": int(citations_match.group(1)) if citations_match else 0,
            "hindex": int(hindex_match.group(1)) if hindex_match else 0,
            "i10index": int(i10index_match.group(1)) if i10index_match else 0
        }
        
        # 2. Estrazione ultime 20 pubblicazioni
        publications = []
        rows = soup.select('.gsc_a_tr')
        
        print(f"Found {len(rows)} publications on Scholar page.")
        
        for row in rows[:20]:
            title_el = row.select_one('.gsc_a_at')
            if not title_el:
                continue
            title = title_el.text.strip()
            
            details = row.select('.gs_gray')
            venue = details[1].text.strip() if len(details) > 1 else "Scientific Publication"
            
            year_el = row.select_one('.gsc_a_y')
            year = year_el.text.strip() if year_el else "N/A"
            
            citations_el = row.select_one('.gsc_a_ac')
            try:
                pub_citations = int(citations_el.text.strip()) if citations_el and citations_el.text.strip() else 0
            except ValueError:
                pub_citations = 0
                
            v_low = venue.lower()
            pub_type = 'paper'
            if 'chapter' in v_low or 'capitolo' in v_low:
                pub_type = 'chapter'
            elif 'book' in v_low or 'libro' in v_low:
                pub_type = 'book'
                
            publications.append({
                "title": title,
                "year": year,
                "venue": venue,
                "citations": pub_citations,
                "type": pub_type
            })
            
        print(f"Successfully retrieved {len(publications)} publications and updated metrics (Citations: {metrics['citations']}, h-index: {metrics['hindex']}).")
        return metrics, publications

    except Exception as e:
        print(f"Error during ScrapingBee execution: {e}")
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
    
    # Check di sicurezza per la chiave API
    if not SCRAPINGBEE_API_KEY:
        print("Error: SCRAPINGBEE_KEY environment variable is missing!")
        sys.exit(1)
        
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            current_data = json.load(f)
        print("Existing data.json loaded successfully.")
    except Exception as e:
        print(f"Error reading data.json: {e}")
        sys.exit(1)

    scholar_metrics, publications = get_scholar_data_via_scrapingbee()
    github_repos = get_github_data()

    if scholar_metrics is not None:
        current_data['scholar'] = scholar_metrics
    if publications is not None and len(publications) > 0:
        current_data['publications'] = publications
    if github_repos is not None:
        current_data['github_repos'] = github_repos

    try:
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
        print("data.json successfully updated with ScrapingBee + GitHub data!")
    except Exception as e:
        print(f"Critical Error writing to data.json: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()