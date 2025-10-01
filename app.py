# app.py (معدل لتحسين الفهم بالكلمات المفتاحية + top-k embeddings)
from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import NearestNeighbors
import google.generativeai as genai
import json
import os
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
genai.configure(api_key="AIzaSyBEeidGnK_uyf9ikJWW9elsAgDdz8t09oA")  # ← ضع هنا API KEY بتاع Gemini

FAQ_PATH = os.path.join(os.path.dirname(__file__), "faq.json")
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# --- معلمات قابلة للتعديل ---
TOP_K = 5
EMB_WEIGHT = 0.7
TOKEN_WEIGHT = 0.3
COMBINED_THRESHOLD = 0.60   # لو أقل من كده، ما نرجعش إجابة مباشرة
EMB_MIN_ACCEPT = 0.62       # حد أدنى للتشابه بالـ embedding لقبول نتيجة حتى لو token overlap قليل
TOKEN_MIN_ACCEPT = 0.15     # حد أدنى لتداخل الكلمات لقبول نتيجة لو الembedding قوي

# قائمة Stopwords عربية بسيطة (وسعها لو تحب)
ARABIC_STOPWORDS = {
    "في","من","ما","هي","ماهي","ما هي","لم","عن","على","و","او","أو",
    "هل","كيف","أين","كم","هذا","هذه","ذلك","تكون","يكون","هو","هي","إلى","ب"
}

# --- متغيرات الذاكرة في الذاكرة (runtime) ---
questions = []
answers = []
token_sets = []   # قائمة مجموعات الكلمات لكل سؤال محفوظ
nn_model = NearestNeighbors(n_neighbors=1, metric="cosine")
last_added_question = None

# --- دوال مساعدة لتطبيع النص واستخراج الكلمات ---
def remove_diacritics(text: str) -> str:
    # يزيل التشكيل (تريليجيات بسيطة)
    return re.sub(r'[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED]', '', text)

def normalize_ar(text: str) -> str:
    t = text.lower()
    t = remove_diacritics(t)
    # أبقي الحروف العربية والمسافات فقط
    t = re.sub(r'[^\u0600-\u06FF\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def tokens_from_text(text: str):
    t = normalize_ar(text)
    toks = [w for w in t.split() if w and w not in ARABIC_STOPWORDS]
    return toks

def token_overlap_score(query_tokens, cand_tokens):
    if not cand_tokens:
        return 0.0
    qset = set(query_tokens)
    cset = set(cand_tokens)
    inter = qset.intersection(cset)
    return len(inter) / max(len(cset), 1)


# --- IO: تحميل و تحديث faq.json و بناء الـ index --- 
def load_faq_data():
    if not os.path.exists(FAQ_PATH):
        return []
    try:
        with open(FAQ_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def build_index_from_memory():
    global questions, answers, token_sets, nn_model
    # إعادة بناء الـ index من القوائم questions/answers
    if not questions:
        return
    embeddings = embedder.encode(questions, show_progress_bar=False)
    k = min(len(questions), TOP_K)
    nn_model = NearestNeighbors(n_neighbors=k, metric="cosine")
    nn_model.fit(embeddings)

def initialize_memory():
    global questions, answers, token_sets
    data = load_faq_data()
    questions = [item["question"] for item in data]
    answers = [item["answer"] for item in data]
    token_sets = [tokens_from_text(q) for q in questions]
    if questions:
        build_index_from_memory()

initialize_memory()


# --- تحديث/حفظ سؤال وإجابة (update إذا مشابه) ---
def save_or_update_qa(question, answer):
    global questions, answers, token_sets

    # تحميل الملف
    if not os.path.exists(FAQ_PATH):
        data = []
    else:
        with open(FAQ_PATH, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except:
                data = []

    q_toks = tokens_from_text(question)
    found_idx = None

    # دور على سؤال مشابه في الذاكرة
    for i, q in enumerate(questions):
        overlap = token_overlap_score(q_toks, token_sets[i])
        if overlap >= 0.6:
            found_idx = i
            break

    # تحديث أو إضافة
    if found_idx is not None:
        old_q = questions[found_idx]
        # عدل في الملف
        updated = False
        for item in data:
            if item["question"].strip() == old_q.strip():
                item["answer"] = answer
                updated = True
                break
        if not updated:
            data.append({"question": question, "answer": answer})
        answers[found_idx] = answer
    else:
        data.append({"question": question, "answer": answer})
        questions.append(question)
        answers.append(answer)
        token_sets.append(q_toks)

    # اكتب الملف من جديد
    with open(FAQ_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # أعد بناء الـ index
    build_index_from_memory()

# --- Scraping بسيط من الصفحة (غيري selectors حسب موقعك) ---
def get_answer_from_url(question):
    url = "https://www.mueen.com.sa/ar/"  # ← عدّليها للصفحة اللي فيها FAQ
    try:
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        # هنا نفترض وجود بلوكات FAQ — عدلي selectors حسب الصفحة الحقيقية
        for block in soup.select(".faq-item"):
            q = block.select_one(".faq-question")
            a = block.select_one(".faq-answer")
            if not q or not a:
                continue
            q_text = q.get_text(strip=True)
            a_text = a.get_text(strip=True)
            # تطبيع ومقارنة بسيطة: كلمة مشتركة واحدة كافية كاختبار أولي
            q_toks = tokens_from_text(q_text)
            user_toks = tokens_from_text(question)
            if token_overlap_score(user_toks, q_toks) > 0:
                return a_text
    except Exception as e:
        print("scraping error:", e)
    return None


# --- دالة البحث الأفضل (top-k + keywords fusion) ---
def get_best_answer(user_input):
    global last_added_question

    user_toks = tokens_from_text(user_input)

    # إذا ما فيش أسئلة محفوظة بعد:
    if not questions:
        # حاول Scrape وجايب جواب؟ خزّنه وارجعه
        scraped = get_answer_from_url(user_input)
        if scraped:
            save_or_update_qa(user_input, scraped)
            return scraped
        # ما لقيناش → خزّن placeholder
        save_or_update_qa(user_input, "سيتم التعديل على الإجابة لاحقاً")
        last_added_question = user_input
        return "لم أجد إجابة مناسبة حالياً، يمكنك أن تخبرني بالرد الصحيح."

    # حساب embeddings و top-k
    q_vec = embedder.encode([user_input])
    k = min(TOP_K, len(questions))
    dist, idxs = nn_model.kneighbors(q_vec, n_neighbors=k)
    best_score = -1.0
    best_idx = None
    best_emb_sim = 0.0
    best_tok_overlap = 0.0

    for rank, cand_idx in enumerate(idxs[0]):
        emb_sim = 1 - dist[0][rank]  # تحويل المسافة إلى تشابه
        cand_toks = token_sets[cand_idx] if cand_idx < len(token_sets) else tokens_from_text(questions[cand_idx])
        tok_overlap = token_overlap_score(user_toks, cand_toks)

        combined = EMB_WEIGHT * emb_sim + TOKEN_WEIGHT * tok_overlap

        if combined > best_score:
            best_score = combined
            best_idx = cand_idx
            best_emb_sim = emb_sim
            best_tok_overlap = tok_overlap

    # قرار إرجاع النتيجة أو لا
    if best_idx is not None and (best_score >= COMBINED_THRESHOLD) and (best_emb_sim >= EMB_MIN_ACCEPT or best_tok_overlap >= TOKEN_MIN_ACCEPT):
        # سجل السؤال والإجابة (توثيق) — نسجل التكرار أيضًا كما طلبتي
        answer = answers[best_idx]
        save_or_update_qa(user_input, answer)
        return answer

    # لو لم نجد نتيجة مطابقة كافية، حاول Scraping
    scraped = get_answer_from_url(user_input)
    if scraped:
        save_or_update_qa(user_input, scraped)
        return scraped

    # أخيرًا: خزّن placeholder وأعلم المستخدم
    save_or_update_qa(user_input, "سيتم التعديل على الإجابة لاحقاً")
    last_added_question = user_input
    return "لم أجد إجابة مناسبة حالياً، يمكنك أن تخبرني بالرد الصحيح."


@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "")
    candidate_answer = get_best_answer(user_input)

    # استخدمي Gemini لصياغة لطيفة إن احتجتي (اختياري)
    try:
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        prompt = (
            f"السؤال: {user_input}\n"
            f"المحتوى المتوفر: {candidate_answer}\n"
            "أعد صياغة إجابة قصيرة وواضحة للمستخدم (سطر واحد)."
        )
        response = model.generate_content(prompt)
        final_reply = response.text.strip().split("\n")[0]
    except Exception:
        # لو فشل الLLM نرجع الإجابة الأولية
        final_reply = candidate_answer

    # خزّني الإجابة النهائية التي ظهرت للمستخدم (توثيق)
    save_or_update_qa(user_input, final_reply)

    return jsonify({"reply": final_reply})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
