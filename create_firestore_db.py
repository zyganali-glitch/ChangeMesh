import google.auth
from google.auth.transport.requests import AuthorizedSession

PROJECT_ID = "project-af5e1c99-3bc4-424f-b53"
REGION = "eur3" # Firestore region ID for europe-west3 is eur3 or europe-west3

def create_firestore():
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    authed_session = AuthorizedSession(credentials)
    
    url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases?databaseId=(default)"
    
    payload = {
        "type": "FIRESTORE_NATIVE",
        "locationId": "europe-west3"
    }
    
    response = authed_session.post(url, json=payload)
    print("Response status:", response.status_code)
    print("Response JSON:", response.text)

if __name__ == "__main__":
    create_firestore()
