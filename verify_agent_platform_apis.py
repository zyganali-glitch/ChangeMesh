import google.auth
from google.auth.transport.requests import AuthorizedSession
import json

PROJECT_ID = "project-af5e1c99-3bc4-424f-b53"

SERVICES_TO_CHECK = {
    "Agent Runtime": "aiplatform.googleapis.com",
    "Memory Bank": "aiplatform.googleapis.com", # Usually part of Vertex AI Extensions/Agent Builder
    "Agent Registry": "aiplatform.googleapis.com",
    "Agent Identity": "iam.googleapis.com", 
    "Agent Gateway": "apigateway.googleapis.com",
    "Model Armor": "modelarmor.googleapis.com",
    "Observability": "logging.googleapis.com"
}

def verify_apis():
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    authed_session = AuthorizedSession(credentials)
    
    print("Verifying Agent Platform APIs...")
    for name, api in SERVICES_TO_CHECK.items():
        url = f"https://serviceusage.googleapis.com/v1/projects/{PROJECT_ID}/services/{api}"
        response = authed_session.get(url)
        
        if response.status_code == 200:
            data = response.json()
            state = data.get("state", "UNKNOWN")
            print(f"  - {name} ({api}): {state}")
        elif response.status_code == 403:
            print(f"  - {name} ({api}): PERMISSION_BLOCKED (403 Forbidden)")
        elif response.status_code == 404:
            print(f"  - {name} ({api}): PREVIEW_BLOCKED or NOT_FOUND (404)")
        else:
            print(f"  - {name} ({api}): ERROR {response.status_code} - {response.text}")

if __name__ == "__main__":
    verify_apis()
