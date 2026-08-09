import json
import requests
import sys

# --- CONFIGURATION ---
# Sostituisci ASSOLUTAMENTE con il tuo vero username tra gli apici
GITHUB_USERNAME = 'il-tuo-username-qui' 

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
    
    # 1. Tenta di leggere il file data.json esistente
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            current_data = json.load(f)
        print("Existing data.json loaded successfully.")
    except Exception as e:
        print(f"Warning: Could not read data.json ({e}). Creating template structure.")
        current_data = {
            "scholar": {"citations": 0, "hindex": 0, "i10index": 0},
            "publications": [],
            "teaching": [],
            "projects": []
        }

    # 2. Recupera i dati di GitHub
    github_repos = get_github_data()

    # 3. Aggiorna la sezione se la chiamata è andata a buon fine
    if github_repos is not None:
        current_data['github_repos'] = github_repos
        print(f"Successfully retrieved {len(github_repos)} public repositories.")
    else:
        print("Skipping GitHub update due to previous errors.")

    # 4. Salva il file data.json aggiornato
    try:
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
        print("data.json successfully written and saved!")
    except Exception as e:
        print(f"Critical Error: Could not write to data.json: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as global_e:
        print(f"Unexpected global execution error: {global_e}")
        sys.exit(1)
