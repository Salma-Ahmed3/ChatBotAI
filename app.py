# ============================================
# 🤖 Chatbot AI — نظام أسئلة وأجوبة ذكي باستخدام Embeddings + الكلمات المفتاحية
# ============================================

from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import NearestNeighbors
import google.generativeai as genai
import json, os, re, requests
from bs4 import BeautifulSoup

# --------------------------------------------
# ⚙️ الإعدادات العامة
# --------------------------------------------
app = Flask(__name__)

# مفتاح Gemini API
genai.configure(api_key="AIzaSyBEeidGnK_uyf9ikJWW9elsAgDdz8t09oA")

# مسار ملف قاعدة البيانات
FAQ_PATH = os.path.join(os.path.dirname(__file__), "faq.json")

# نموذج Embeddings خفيف وسريع
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# --------------------------------------------
# ⚙️ الإعدادات القابلة للتخصيص
# --------------------------------------------
TOP_K = 5
EMB_WEIGHT = 0.7
TOKEN_WEIGHT = 0.3
COMBINED_THRESHOLD = 0.60

# --------------------------------------------
# 🚫 الكلمات الشائعة (Stopwords)
# --------------------------------------------
ARABIC_STOPWORDS = {
    "في", "من", "ما", "هي", "ماهي", "ما هي", "لم", "عن", "على", "و", "او", "أو",
    "هل", "كيف", "أين", "كم", "هذا", "هذه", "ذلك", "تكون", "يكون", "هو", "هي", "إلى", "ب"
}

# --------------------------------------------
# 🧠 متغيرات الذاكرة أثناء التشغيل
# --------------------------------------------
questions, answers, token_sets = [], [], []
nn_model = NearestNeighbors(n_neighbors=1, metric="cosine")

# --------------------------------------------
# 🧹 دوال مساعدة
# --------------------------------------------

def remove_diacritics(text):
    return re.sub(r'[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED]', '', text)

def normalize_ar(text):
    t = text.lower()
    t = remove_diacritics(t)
    t = re.sub(r'[^\u0600-\u06FF\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

def tokens_from_text(text):
    t = normalize_ar(text)
    return [w for w in t.split() if w and w not in ARABIC_STOPWORDS]

def token_overlap_score(q_tokens, c_tokens):
    if not c_tokens:
        return 0.0
    return len(set(q_tokens) & set(c_tokens)) / max(len(c_tokens), 1)

# --------------------------------------------
# 💾 تحميل وتحديث قاعدة البيانات
# --------------------------------------------
def load_faq_data():
    if not os.path.exists(FAQ_PATH):
        return []
    try:
        with open(FAQ_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def build_index_from_memory():
    global nn_model
    if not questions:
        return
    embeddings = embedder.encode(questions, show_progress_bar=False)
    nn_model = NearestNeighbors(n_neighbors=min(len(questions), TOP_K), metric="cosine")
    nn_model.fit(embeddings)

def initialize_memory():
    global questions, answers, token_sets
    data = load_faq_data()
    questions[:] = [d["question"] for d in data]
    answers[:] = [d["answer"] for d in data]
    token_sets[:] = [tokens_from_text(q) for q in questions]
    if questions:
        build_index_from_memory()
        print(f"✅ تم تحميل {len(questions)} سؤال وبناء الفهرس بنجاح.")
    else:
        print("⚠️ لا توجد أسئلة محفوظة بعد.")

initialize_memory()

# --------------------------------------------
# ✍️ حفظ أو تحديث سؤال/إجابة
# --------------------------------------------
def save_or_update_qa(question, answer):
    data = load_faq_data()
    q_tokens = tokens_from_text(question)
    found_idx = None

    for i, q in enumerate(questions):
        if token_overlap_score(q_tokens, token_sets[i]) >= 0.6:
            found_idx = i
            break

    if found_idx is not None:
        old_q = questions[found_idx]
        for item in data:
            if item["question"].strip() == old_q.strip():
                item["answer"] = answer
                break
        answers[found_idx] = answer
    else:
        data.append({"question": question, "answer": answer})
        questions.append(question)
        answers.append(answer)
        token_sets.append(q_tokens)

    with open(FAQ_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    build_index_from_memory()

# --------------------------------------------
# 🔍 البحث الذكي مع دعم الترجمة
# --------------------------------------------
def get_best_answer(user_input):
    """
    البحث عن أفضل إجابة — مع ترجمة ذكية:
    - يترجم السؤال إلى العربية للبحث.
    - بعد إيجاد الإجابة بالعربية، يترجم الرد إلى نفس لغة المستخدم.
    - يرجع فقط الترجمة بدون أي مقدمة أو شرح.
    """
    global last_added_question
    original_text = user_input
    answer = ""

    # ---------------------------
    # 🔹 تحديد لغة المستخدم
    # ---------------------------
    detected_lang = "Arabic"
    try:
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        resp = model.generate_content(
            f"Detect the language of this text only. Reply with one word like: Arabic, English, French, etc.\n\n{user_input}"
        )
        detected_lang = resp.text.strip().capitalize()
        print(f"🌍 اللغة المكتشفة: {detected_lang}")
    except Exception as e:
        print("⚠️ فشل في تحديد اللغة:", e)

    # ---------------------------
    # 🔹 ترجمة السؤال إلى العربية للبحث فقط
    # ---------------------------
    translated_for_search = user_input
    if detected_lang.lower() != "arabic":
        try:
            model = genai.GenerativeModel("models/gemini-2.5-pro")
            prompt = (
                "Translate the following text to Arabic. "
                "Reply ONLY with the translated Arabic text, no explanations, no notes, no markdown:\n\n"
                f"{user_input}"
            )
            resp = model.generate_content(prompt)
            translated_for_search = re.sub(
                r"(?i)(here is the translation|translation|of course|sure|the answer is|:)",
                "",
                resp.text.strip(),
            ).strip()
            print(f"🌐 [ترجمة السؤال] {user_input} → {translated_for_search}")
        except Exception as e:
            print("⚠️ خطأ أثناء ترجمة السؤال:", e)

    # ---------------------------
    # 🔍 البحث في قاعدة الأسئلة بالعربية
    # ---------------------------
    user_toks = tokens_from_text(translated_for_search)

    if not questions:
        answer = "لم أجد إجابة مناسبة حالياً، يمكنك تزويدي بالإجابة الصحيحة."
        save_or_update_qa(translated_for_search, answer)
    else:
        q_vec = embedder.encode([translated_for_search])
        k = min(TOP_K, len(questions))
        dist, idxs = nn_model.kneighbors(q_vec, n_neighbors=k)

        best_idx, best_score = None, -1
        for rank, cand_idx in enumerate(idxs[0]):
            emb_sim = 1 - dist[0][rank]
            tok_overlap = token_overlap_score(user_toks, token_sets[cand_idx])
            combined = EMB_WEIGHT * emb_sim + TOKEN_WEIGHT * tok_overlap
            if combined > best_score:
                best_score = combined
                best_idx = cand_idx

        if best_idx is not None and best_score >= COMBINED_THRESHOLD:
            answer = answers[best_idx]
        else:
            answer = "لم أجد إجابة مناسبة حالياً، يمكنك تزويدي بالإجابة الصحيحة."

    # ---------------------------
    # 🔹 ترجمة الإجابة إلى نفس لغة المستخدم
    # ---------------------------
    final_answer = answer
    if detected_lang.lower() != "arabic":
        try:
            model = genai.GenerativeModel("models/gemini-2.5-pro")
            prompt = (
                f"Translate the following Arabic text to {detected_lang}. "
                "Reply ONLY with the translated text itself, no explanations, no markdown, no intro phrases:\n\n"
                f"{answer}"
            )
            resp = model.generate_content(prompt)
            translated_answer = re.sub(
                r"(?i)(here is the translation|translation|of course|sure|the answer is|:)",
                "",
                resp.text.strip(),
            ).strip()
            if translated_answer:
                print(f"🌐 [ترجمة الإجابة] {answer} → {translated_answer}")
                final_answer = translated_answer
        except Exception as e:
            print("⚠️ خطأ أثناء ترجمة الإجابة:", e)

    # ---------------------------
    # 💾 نحفظ النسخة العربية فقط
    # ---------------------------
    try:
        save_or_update_qa(translated_for_search, answer)
    except Exception as e:
        print("⚠️ فشل أثناء الحفظ:", e)

    return final_answer

# --------------------------------------------
# 💬 واجهة الدردشة (API)
# --------------------------------------------
@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "")
    session_id = request.json.get("session_id", "default")

    reply = get_best_answer(user_input)
    return jsonify({"reply": reply})

# --------------------------------------------
# 🚀 تشغيل الخادم
# --------------------------------------------
if __name__ == "__main__":
    app.run(port=5000, debug=True)
