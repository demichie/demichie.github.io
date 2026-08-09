import json
import requests
import sys

# --- CONFIGURATION ---
GITHUB_USERNAME = 'demichie' 

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
    
    # 1. Read existing data.json
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            current_data = json.load(f)
        print("Existing data.json loaded successfully.")
    except Exception as e:
        print(f"Error reading data.json: {e}")
        sys.exit(1)

    # 2. Fetch GitHub data
    github_repos = get_github_data()

    # 3. Update GitHub section if successful
    if github_repos is not None:
        current_data['github_repos'] = github_repos
        print(f"Successfully retrieved {len(github_repos)} public repositories.")
    else:
        print("Skipping GitHub update due to errors.")

    # 4. Save updated data.json
    try:
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
        print("data.json successfully updated!")
    except Exception as e:
        print(f"Critical Error writing to data.json: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()