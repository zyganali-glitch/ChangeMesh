import google.auth
from google.auth.transport.requests import AuthorizedSession
import sys

PROJECT_ID = "project-af5e1c99-3bc4-424f-b53"
API = "apigateway.googleapis.com"

def enable_api():
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    authed_session = AuthorizedSession(credentials)
    
    print(f"Attempting to enable {API}...")
    url = f"https://serviceusage.googleapis.com/v1/projects/{PROJECT_ID}/services/{API}:enable"
    response = authed_session.post(url)
    
    if response.status_code == 200:
        print(f"Success: {response.json()}")
    else:
        print(f"Error {response.status_code}: {response.text}")
        sys.exit(1)

if __name__ == "__main__":
    enable_api()
