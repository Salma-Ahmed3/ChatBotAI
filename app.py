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
genai.configure(api_key="AIzaSyDyHN4DInZrAHrUHbObZchZGS21VEEKBoU")

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
    
    # Reset lists
    questions.clear()
    answers.clear()
    token_sets.clear()
    
    # Extract questions and answers from nested structure
    for topic in data:
        for qa in topic.get("questions", []):
            question = qa.get("question", "")
            answer_list = qa.get("answers", [])
            
            if question and answer_list:
                questions.append(question)
                # Join multiple answers with newline if there are multiple
                answers.append("\n".join(answer_list))
                token_sets.append(tokens_from_text(question))
    
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
    found_topic = None

    # البحث عن سؤال مشابه
    for topic in data:
        for qa in topic.get("questions", []):
            if token_overlap_score(q_tokens, tokens_from_text(qa["question"])) >= 0.6:
                found_topic = topic
                found_idx = data.index(topic)
                break
        if found_topic:
            break

    # تحويل الإجابة إلى قائمة إذا كانت نصاً
    answer_list = answer.split("\n") if isinstance(answer, str) else answer

    if found_topic:
        # تحديث السؤال الموجود
        for qa in found_topic["questions"]:
            if token_overlap_score(q_tokens, tokens_from_text(qa["question"])) >= 0.6:
                qa["answers"] = answer_list
                break
    else:
        # إنشاء موضوع جديد
        new_topic = {
            "topic": extract_topic(question),  # دالة مساعدة سنضيفها
            "questions": [{
                "question": question,
                "answers": answer_list
            }]
        }
        data.append(new_topic)

    # تحديث الملف
    with open(FAQ_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # تحديث الذاكرة
    initialize_memory()

def extract_topic(question):
    """استخراج الموضوع من السؤال"""
    # إزالة كلمات الاستفهام الشائعة
    topic = question.replace("ما هي", "").replace("ما هو", "").replace("؟", "").strip()
    # أخذ أول 3 كلمات كموضوع
    words = topic.split()[:3]
    return " ".join(words)

# --------------------------------------------
# 🔍 البحث الذكي مع دعم الترجمة
# --------------------------------------------
def get_best_answer(user_input):
    """
    البحث عن أفضل إجابة مع دعم الكلمات المفتاحية والترجمة
    """
    original_text = user_input
    answer = ""

    # ---------------------------
    # 🔹 تحديد لغة المستخدم والترجمة
    # ---------------------------
    detected_lang = "Arabic"
    try:
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        resp = model.generate_content(
            f"Detect the language of this text only. Reply with one word like: Arabic, English, French, etc.\n\n{user_input}"
        )
        detected_lang = resp.text.strip().capitalize()
    except Exception as e:
        print("⚠️ فشل في تحديد اللغة:", e)

    # ترجمة السؤال إلى العربية إذا لزم الأمر
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

        except Exception as e:
            print("⚠️ خطأ أثناء الترجمة:", e)

    # ---------------------------
    # 🔍 البحث الذكي بالكلمات المفتاحية
    # ---------------------------
    if not questions:
        answer = "لم أجد إجابة مناسبة حالياً."
    else:
        # استخراج الكلمات المفتاحية
        keywords = [w.strip("؟,.،") for w in translated_for_search.split() if len(w) > 3]
        
        # البحث باستخدام Embeddings
        q_vec = embedder.encode([translated_for_search])
        k = min(TOP_K, len(questions))
        dist, idxs = nn_model.kneighbors(q_vec, n_neighbors=k)

        candidates = []
        for rank, idx in enumerate(idxs[0]):
            emb_sim = 1 - dist[0][rank]
            # فحص تطابق الكلمات المفتاحية
            keyword_match = False
            for keyword in keywords:
                if (keyword in questions[idx].lower() or 
                    keyword in answers[idx].lower()):
                    keyword_match = True
                    break
            
            if keyword_match and emb_sim >= COMBINED_THRESHOLD:
                candidates.append((emb_sim, answers[idx]))

        if candidates:
            # اختيار أفضل إجابة بناءً على التشابه
            candidates.sort(reverse=True)
            answer = candidates[0][1]
        else:
            answer = "لم أجد إجابة مناسبة حالياً."

    # ---------------------------
    # 🔹 ترجمة الإجابة إلى لغة المستخدم
    # ---------------------------
    final_answer = answer
    if detected_lang.lower() != "arabic":
        try:
            model = genai.GenerativeModel("models/gemini-2.5-pro")
            prompt = (
                 "Translate the following text to Arabic. "
                 "Reply ONLY with the translated Arabic text, no explanations, no notes, no markdown:\n\n"
                f"Translate the following Arabic text to {detected_lang}:\n\n{answer}"
            )
            resp = model.generate_content(prompt)
            clean_text = re.sub(
            r"(?i)(here is the translation|of course|translation|sure|the answer is|Here is the English|:)",
            "",
            resp.text.strip()
            ).strip()
            final_answer = clean_text

        except Exception as e:
            print("⚠️ خطأ أثناء ترجمة الإجابة:", e)

    # حفظ السؤال والإجابة
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
