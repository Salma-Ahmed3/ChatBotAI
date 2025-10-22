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
