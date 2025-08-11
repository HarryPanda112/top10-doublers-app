# firebase_utils.py
import os
import json
from dotenv import load_dotenv

load_dotenv()

import firebase_admin
from firebase_admin import credentials, firestore

def _get_default_sa_path():
    # allow env override
    return os.environ.get("FIREBASE_KEY_PATH", os.path.join(os.path.dirname(__file__), "serviceAccountKey.json"))

def init_firebase(sa_path: str | None = None):
    """
    Initialize Firebase Admin SDK (idempotent).
    Returns the initialized app object.
    """
    # if already initialized return the existing app
    if firebase_admin._apps:
        try:
            return firebase_admin.get_app()
        except Exception:
            # fallback to first app in dict if get_app() somehow fails
            return next(iter(firebase_admin._apps.values()))

    if sa_path is None:
        sa_path = _get_default_sa_path()

    if not os.path.exists(sa_path):
        raise FileNotFoundError(f"Firebase service account file not found at: {sa_path}")

    # quick JSON sanity check for clearer error if file is corrupt/empty
    try:
        with open(sa_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise ValueError(f"Service account file at {sa_path} is empty.")
            json.loads(content)
    except json.JSONDecodeError as je:
        raise ValueError(f"Service account JSON decode error for file {sa_path}: {je}") from je

    cred = credentials.Certificate(sa_path)
    app = firebase_admin.initialize_app(cred)
    return app

def get_secret(field_name: str, collection: str = "config", doc_id: str = "keys", sa_path: str | None = None):
    """
    Fetch a secret. Priority:
      1) Environment variable (os.getenv(field_name))
      2) Firestore document: collection/doc_id (requires service account JSON)

    Returns the value or None if not found.
    Raises only for fatal errors (like invalid service account file).
    """
    # 1) env var fallback (convenient for local dev)
    env_val = os.getenv(field_name)
    if env_val:
        return env_val

    # 2) Firestore
    try:
        app = init_firebase(sa_path=sa_path)
    except Exception as e:
        # do not crash the whole app here; return None but log a clear message
        # Caller can decide how to behave when None is returned.
        raise RuntimeError(f"Failed to initialize Firebase Admin SDK: {e}") from e

    try:
        db = firestore.client()
        doc_ref = db.collection(collection).document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        return data.get(field_name)
    except Exception as e:
        raise RuntimeError(f"Failed to read secret '{field_name}' from Firestore: {e}") from e
