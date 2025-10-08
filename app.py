# ============================================
# 🤖 chatbot AI - FAQ System using Embeddings + Keywords
# ============================================

from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import NearestNeighbors
import google.generativeai as genai
import json, os, re, requests
from bs4 import BeautifulSoup

# --------------------------------------------
#  إعدادات عامة
# --------------------------------------------
app = Flask(__name__)

# مفتاح واجهة Gemini
genai.configure(api_key="AIzaSyBEeidGnK_uyf9ikJWW9elsAgDdz8t09oA")

# مسار ملف الأسئلة والإجابات
FAQ_PATH = os.path.join(os.path.dirname(__file__), "faq.json")

# نموذج تحويل النصوص إلى Embeddings (نموذج خفيف وسريع)
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# --------------------------------------------
#  معلمات يمكن تعديلها
# --------------------------------------------
TOP_K = 5                # كم نتيجة يبحث عنها في كل مرة
EMB_WEIGHT = 0.7         # وزن تشابه الـ Embeddings
TOKEN_WEIGHT = 0.3       # وزن تطابق الكلمات
COMBINED_THRESHOLD = 0.60
EMB_MIN_ACCEPT = 0.62
TOKEN_MIN_ACCEPT = 0.15

# --------------------------------------------
#  كلمات شائعة (Stopwords) يتم تجاهلها في البحث
# --------------------------------------------
ARABIC_STOPWORDS = {
    "في", "من", "ما", "هي", "ماهي", "ما هي", "لم", "عن", "على", "و", "او", "أو",
    "هل", "كيف", "أين", "كم", "هذا", "هذه", "ذلك", "تكون", "يكون", "هو", "هي", "إلى", "ب"
}

# --------------------------------------------
#  متغيرات الذاكرة في runtime
# --------------------------------------------
questions = []
answers = []
token_sets = []
nn_model = NearestNeighbors(n_neighbors=1, metric="cosine")
last_added_question = None

# --------------------------------------------
#  دوال مساعدة لتنظيف وتحليل النص
# --------------------------------------------

def remove_diacritics(text: str) -> str:
    """إزالة التشكيل من النص العربي"""
    return re.sub(r'[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED]', '', text)

def normalize_ar(text: str) -> str:
    """تحويل النص لحروف عربية فقط بدون رموز أو تشكيل"""
    t = text.lower()
    t = remove_diacritics(t)
    t = re.sub(r'[^\u0600-\u06FF\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

def tokens_from_text(text: str):
    """استخراج الكلمات الهامة فقط (بدون stopwords)"""
    t = normalize_ar(text)
    return [w for w in t.split() if w and w not in ARABIC_STOPWORDS]

def token_overlap_score(query_tokens, cand_tokens):
    """حساب نسبة تداخل الكلمات بين سؤالين"""
    if not cand_tokens:
        return 0.0
    qset, cset = set(query_tokens), set(cand_tokens)
    return len(qset.intersection(cset)) / max(len(cset), 1)

# --------------------------------------------
#  تحميل وتحديث قاعدة البيانات
# --------------------------------------------

def load_faq_data():
    """قراءة ملف faq.json"""
    if not os.path.exists(FAQ_PATH):
        return []
    try:
        with open(FAQ_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def build_index_from_memory():
    """إعادة بناء نموذج البحث (index)"""
    global nn_model
    if not questions:
        return
    embeddings = embedder.encode(questions, show_progress_bar=False)
    k = min(len(questions), TOP_K)
    nn_model = NearestNeighbors(n_neighbors=k, metric="cosine")
    nn_model.fit(embeddings)

def initialize_memory():
    """تحميل البيانات عند بدء التشغيل"""
    global questions, answers, token_sets
    data = load_faq_data()
    questions = [d["question"] for d in data]
    answers = [d["answer"] for d in data]
    token_sets = [tokens_from_text(q) for q in questions]
    if questions:
        build_index_from_memory()
        print(f" تم تحميل {len(questions)} سؤال من قاعدة البيانات.")
        print(" تم بناء موديل الأسئلة (Embeddings index) بنجاح.")
    else:
        print(" لا توجد أسئلة محفوظة بعد.")

initialize_memory()

# --------------------------------------------
#  تحديث أو إضافة سؤال جديد
# --------------------------------------------

def save_or_update_qa(question, answer):
    """تحديث أو إضافة سؤال جديد لقاعدة البيانات"""
    global questions, answers, token_sets

    data = load_faq_data()
    q_toks = tokens_from_text(question)
    found_idx = None

    # فحص وجود سؤال مشابه
    for i, q in enumerate(questions):
        if token_overlap_score(q_toks, token_sets[i]) >= 0.6:
            found_idx = i
            break

    # لو موجود: حدث الإجابة
    if found_idx is not None:
        old_q = questions[found_idx]
        for item in data:
            if item["question"].strip() == old_q.strip():
                item["answer"] = answer
                break
        answers[found_idx] = answer
    else:
        # لو غير موجود: أضف سؤال جديد
        data.append({"question": question, "answer": answer})
        questions.append(question)
        answers.append(answer)
        token_sets.append(q_toks)

    # حفظ الملف
    with open(FAQ_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    build_index_from_memory()

# --------------------------------------------
#  Web Scraping بسيط (اختياري)
# --------------------------------------------

def get_answer_from_url(question):
    """محاولة استخراج الإجابة من موقع خارجي (كمصدر بديل)"""
    url = "https://www.mueen.com.sa/ar/"
    try:
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        for block in soup.select(".faq-item"):
            q = block.select_one(".faq-question")
            a = block.select_one(".faq-answer")
            if q and a:
                q_text, a_text = q.get_text(strip=True), a.get_text(strip=True)
                if token_overlap_score(tokens_from_text(question), tokens_from_text(q_text)) > 0:
                    return a_text
    except Exception as e:
        print("scraping error:", e)
    return None

# --------------------------------------------
#  البحث عن أفضل إجابة (core logic)
# --------------------------------------------

def get_best_answer(user_input):
    """البحث في الموديل للعثور على أقرب إجابة"""
    global last_added_question

    user_toks = tokens_from_text(user_input)

    # لو ما فيش أسئلة بعد
    if not questions:
        scraped = get_answer_from_url(user_input)
        if scraped:
            save_or_update_qa(user_input, scraped)
            return scraped
        save_or_update_qa(user_input, "سيتم التعديل على الإجابة لاحقاً")
        return "لم أجد إجابة مناسبة حالياً، يمكنك أن تخبرني بالرد الصحيح."

    # حساب الـ Embedding للسؤال الجديد
    q_vec = embedder.encode([user_input])
    k = min(TOP_K, len(questions))
    dist, idxs = nn_model.kneighbors(q_vec, n_neighbors=k)

    best_idx, best_score = None, -1

    for rank, cand_idx in enumerate(idxs[0]):
        emb_sim = 1 - dist[0][rank]  # تحويل المسافة إلى تشابه
        tok_overlap = token_overlap_score(user_toks, token_sets[cand_idx])
        combined = EMB_WEIGHT * emb_sim + TOKEN_WEIGHT * tok_overlap
        if combined > best_score:
            best_score = combined
            best_idx = cand_idx

    # لو النتيجة قوية بما يكفي
    if best_idx is not None and best_score >= COMBINED_THRESHOLD:
        answer = answers[best_idx]
        save_or_update_qa(user_input, answer)
        return answer

    # تجربة Web Scraping كمصدر بديل
    scraped = get_answer_from_url(user_input)
    if scraped:
        save_or_update_qa(user_input, scraped)
        return scraped

    # لو مفيش حاجة، نحفظ placeholder
    save_or_update_qa(user_input, "سيتم التعديل على الإجابة لاحقاً")
    return "لم أجد إجابة مناسبة حالياً، يمكنك أن تخبرني بالرد الصحيح."
# --------------------------------------------
#  إدارة الذاكرة لكل مستخدم
# --------------------------------------------

user_memory = {}  # {session_id: [history_list]}

def add_to_memory(session_id, message, reply):
    """حفظ آخر تفاعلات المستخدم"""
    if session_id not in user_memory:
        user_memory[session_id] = []
    user_memory[session_id].append({"q": message, "a": reply})
    # نحافظ على آخر 5 فقط
    if len(user_memory[session_id]) > 5:
        user_memory[session_id] = user_memory[session_id][-5:]

def get_memory_context(session_id):
    """إرجاع آخر 3 أسئلة لتغذية الذكاء"""
    if session_id not in user_memory:
        return ""
    history = user_memory[session_id][-3:]
    context = ""
    for h in history:
        context += f"المستخدم: {h['q']}\nالبوت: {h['a']}\n"
    return context

# --------------------------------------------
#  API: Endpoint الدردشة
# --------------------------------------------

@app.route("/chat", methods=["POST"])
def chat():
    """النقطة الأساسية للتخاطب مع البوت"""
    user_input = request.json.get("message", "")
    session_id = request.json.get("session_id", "default")  # لو التطبيق فيه مستخدمين متعددين

    candidate_answer = get_best_answer(user_input)

    # الحصول على ذاكرة المستخدم السابقة
    context = get_memory_context(session_id)

    # تحسين الرد مع أخذ السياق في الاعتبار
    try:
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        prompt = (
            "سياق المحادثة السابقة:\n" + context +
            f"\nالسؤال الحالي: {user_input}\n"
            f"الإجابة المقترحة من قاعدة البيانات: {candidate_answer}\n"
            "استخدم السياق السابق لفهم المقصود ورد بإجابة دقيقة ومترابطة، مختصرة وواضحة."
        )
        response = model.generate_content(prompt)
        final_reply = response.text.strip().split("\n")[0]
    except Exception:
        final_reply = candidate_answer

    # حفظ التفاعل في الذاكرة والملف
    save_or_update_qa(user_input, final_reply)
    add_to_memory(session_id, user_input, final_reply)

    return jsonify({"reply": final_reply})


# --------------------------------------------
#  تشغيل السيرفر
# --------------------------------------------
if __name__ == "__main__":
    app.run(port=5000, debug=True)
