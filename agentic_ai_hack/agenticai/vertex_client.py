from google.oauth2 import service_account
import google.auth.transport.requests

# Path to your service account JSON file
KEY_PATH = "./agenticai/service_account.json"
# Scopes needed for Vertex AI
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

# Load credentials
credentials = service_account.Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES)

# Refresh and get token
auth_req = google.auth.transport.requests.Request()
credentials.refresh(auth_req)

access_token = credentials.token

def query_vertex_ai(payload):
    import requests

    ENDPOINT_URL = (
        "https://aiplatform.googleapis.com/v1/projects/kanyarasi/locations/global/"
        "publishers/google/models/gemini-2.0-flash-001:generateContent"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(ENDPOINT_URL, headers=headers, json=payload)

    if response.status_code == 200:
        return response.json()
    else:
        return {"error": "Failed to get response from Vertex AI", "status_code": response.status_code}