import os
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import NearestNeighbors
import json

# Simple per-workspace user-state storage (single default user)
USER_STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "user_state.json")
SUBMISSIONS_PATH = os.path.join(os.path.dirname(__file__), "..", "user_submissions.json")

QUESTIONS = []
ANSWERS = []
TOKEN_SETS = []
NN_MODEL = NearestNeighbors(n_neighbors=1, metric="cosine")
EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")

FAQ_PATH = os.path.join(os.path.dirname(__file__), "..", "faq_data.json")
TOP_K = 5
EMB_WEIGHT = 0.7
TOKEN_WEIGHT = 0.3
COMBINED_THRESHOLD = 0.60

# Session history handling.
# By default we persist session history to a file so the chat remains
# while the app process is running and across quick restarts if desired.
PERSIST_SESSION = True
SESSION_FILE = os.path.join(os.path.dirname(__file__), "..", "session_history.json")

# In-memory cache of session history
SESSION_HISTORY = []


def _load_session_from_disk():
	try:
		if PERSIST_SESSION and os.path.exists(SESSION_FILE):
			with open(SESSION_FILE, "r", encoding="utf-8") as f:
				data = json.load(f)
				if isinstance(data, list):
					return data
	except Exception as e:
		print(f"⚠️ failed loading session from disk: {e}")
	return []


def _write_session_to_disk():
	try:
		if PERSIST_SESSION:
			with open(SESSION_FILE, "w", encoding="utf-8") as f:
				json.dump(SESSION_HISTORY, f, ensure_ascii=False, indent=2)
	except Exception as e:
		print(f"⚠️ failed writing session to disk: {e}")


# Load existing session on import (if persistence enabled)
try:
	loaded = _load_session_from_disk()
	if isinstance(loaded, list) and loaded:
		SESSION_HISTORY.extend(loaded)
except Exception:
	# already logged in loader
	pass


def append_session_message(role: str, text: str, ts: int = None):
	"""Append a message to the in-memory session history.

	role: 'user' or 'bot'
	text: message text
	ts: optional unix timestamp (int). If None, will use current time.
	"""
	try:
		if ts is None:
			import time

			ts = int(time.time())
		entry = {"role": role, "text": text, "ts": ts}
		SESSION_HISTORY.append(entry)
		# persist immediately so the Flutter app can fetch it reliably
		_write_session_to_disk()
	except Exception as e:
		print(f"⚠️ failed appending session message: {e}")


def get_session_history():
	"""Return a copy of the current session history (list of message dicts)."""
	try:
		# return a shallow copy to avoid accidental external mutation
		return list(SESSION_HISTORY)
	except Exception:
		return []


def clear_session_history():
	"""Clear in-memory session history."""
	try:
		SESSION_HISTORY.clear()
		# update the persisted file as well
		_write_session_to_disk()
	except Exception as e:
		print(f"⚠️ failed clearing session history: {e}")


def read_user_state():
	try:
		if not os.path.exists(USER_STATE_PATH):
			with open(USER_STATE_PATH, "w", encoding="utf-8") as f:
				json.dump({"default": {"phase": "select_sector", "sector": None}}, f, ensure_ascii=False, indent=2)
		with open(USER_STATE_PATH, "r", encoding="utf-8") as f:
			return json.load(f)
	except Exception:
		return {"default": {"phase": "select_sector", "sector": None}}


def write_user_state(state):
	try:
		with open(USER_STATE_PATH, "w", encoding="utf-8") as f:
			json.dump(state, f, ensure_ascii=False, indent=2)
	except Exception as e:
		print(f"⚠️ failed writing user state: {e}")


def get_user_state(key="default"):
	s = read_user_state()
	return s.get(key, {"phase": "select_sector", "sector": None})


def set_user_state(data, key="default"):
	s = read_user_state()
	s[key] = data
	write_user_state(s)


def save_submission(entry: dict):
	try:
		submissions = []
		if os.path.exists(SUBMISSIONS_PATH):
			with open(SUBMISSIONS_PATH, "r", encoding="utf-8") as f:
				submissions = json.load(f)
		submissions.append(entry)
		with open(SUBMISSIONS_PATH, "w", encoding="utf-8") as f:
			json.dump(submissions, f, ensure_ascii=False, indent=2)
	except Exception as e:
		print(f"⚠️ failed saving submission: {e}")
