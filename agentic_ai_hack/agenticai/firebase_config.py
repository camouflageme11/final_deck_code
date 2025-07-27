import firebase_admin
from firebase_admin import credentials, firestore

# Path to your Firebase service account key
cred = credentials.Certificate(r"agentic_ai_hack/agenticai/firebase-key.json")
firebase_admin.initialize_app(cred)

db = firestore.client()
