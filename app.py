# ============================================
# 🤖 Chatbot AI — نظام أسئلة وأجوبة ذكي باستخدام Embeddings + الكلمات المفتاحية
# ============================================

from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import NearestNeighbors
import google.generativeai as genai
import json, os, re, requests
from bs4 import BeautifulSoup
from bidi.algorithm import get_display

# --------------------------------------------
# ⚙️ الإعدادات العامة
# --------------------------------------------
app = Flask(__name__)

# مفتاح Gemini API
genai.configure(api_key="AIzaSyBiVujRK7sBtyHN6ttxewS_2lMzvBEIk1A")

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
import time  # ← ضيفها فوق في بداية الملف

def get_best_answer(user_input):
    original_text = user_input
    answer = ""

    # ---------------------------
    # 🔹 تحديد اللغة + الرد على الترحيب بنفس اللغة
    # ---------------------------
    t1 = time.time()
    model = genai.GenerativeModel("models/gemini-2.5-pro")
    try:
        resp = model.generate_content(
            f"""
            You are a multilingual assistant.
            Step 1️⃣: Detect the language of this text.
            Step 2️⃣: If the text is only a greeting (like hello, hi, مرحبا, hola, bonjour, etc.), 
            then reply in the same detected language with a warm greeting message followed by "How can I help you today?" in that language.
            Step 3️⃣: Otherwise, just reply with the language name only (Arabic, English, French, etc.).
            
            User text:
            {user_input}
            """
        )

        detected_text = resp.text.strip()

        # ✅ إذا كانت النتيجة جملة ترحيب كاملة (وليس فقط اسم لغة)
        if any(word in detected_text.lower() for word in ["help", "مساعدتك", "aider", "ayudar", "aiutare"]):
            return detected_text  # الرد الترحيبي الجاهز من Gemini

        # ✅ وإلا فهي مجرد اسم لغة (زي "Arabic", "English" ...)
        detected_lang = detected_text.split()[0].capitalize()

    except Exception as e:
        print("⚠️ فشل في تحديد اللغة أو الرد الترحيبي:", e)
        detected_lang = "Arabic"

    # ---------------------------
    # 🔹 ترجمة السؤال للعربية إذا لزم الأمر
    # ---------------------------
    t2 = time.time()
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
    # 🏙️ التحقق من الأحياء والعناوين
    # ---------------------------
    data = load_faq_data()
    normalized_q = normalize_ar(translated_for_search)

    if "حي" in normalized_q or "احياء" in normalized_q or "العناوين" in normalized_q:
        for topic in data:
            if normalize_ar(topic.get("topic", "")) == "العناوين":
                # الوصول للأسئلة داخل التوبيك
                questions_list = topic.get("questions", [])
                if not questions_list:
                    break

                # استخراج المدن من أول إجابة
                cities = questions_list[0].get("answers", [])
                city_text = " ".join(cities)
                cities_cleaned = [
                    c.strip().replace("،", "").replace(".", "")
                    for c in city_text.split()
                    if len(c.strip()) > 1
                ]

                # 🔹 نبحث عن أي مدينة موجودة في السؤال
                for city in cities_cleaned:
                    if normalize_ar(city) in normalized_q:
                        # نلاقي التوبيك الخاص بالمدينة
                        for sub_topic in data:
                            if normalize_ar(sub_topic.get("topic", "")) == f"العناوين {normalize_ar(city)}":
                                areas = []
                                for q in sub_topic.get("questions", []):
                                    for ans in q.get("answers", []):
                                        areas.extend(ans.replace("،", ",").split(","))
                                areas = [a.strip() for a in areas if a.strip()]

                                # 🔹 نبحث عن الحي داخل السؤال
                                for area in areas:
                                    if normalize_ar(area) in normalized_q:
                                        return f"نعم، حي {area} موجود ✅"

                                # 🔹 لو الحي مش موجود في المدينة المطلوبة
                                return (
                                    f"الحي المطلوب غير موجود في {city} ❌\n"
                                    f"هل ترغب أن أظهر لك الأحياء المتوفرة في {city}؟\n\n"
                                    "اكتب اسم المدينة الآن وسأعرضها لك 👇"
                                )

                # 🔹 لو السؤال عن حي بدون ذكر مدينة
                all_areas = []
                for sub_topic in data:
                    if normalize_ar(sub_topic.get("topic", "")).startswith("العناوين"):
                        for q in sub_topic.get("questions", []):
                            for ans in q.get("answers", []):
                                all_areas.extend(ans.replace("،", ",").split(","))
                all_areas = [a.strip() for a in all_areas if a.strip()]

                for area in all_areas:
                    if normalize_ar(area) in normalized_q:
                        return f"نعم، حي {area} موجود ✅"

                # 🔹 لو الحي غير موجود تمامًا
                return (
                    "الحي المطلوب غير موجود ❌\n"
                    "من فضلك اختر المدينة لمعرفة الأحياء المتوفرة فيها 👇\n\n"
                    "المدن المتاحة: الرياض، جدة، المدينة المنورة"
                )

    # ---------------------------
    # 🔍 البحث الذكي بالكلمات المفتاحية
    # ---------------------------
    t3 = time.time()
    if not questions:
        answer = "لم أجد إجابة مناسبة حالياً."
    else:
        keywords = [w.strip("؟,.،") for w in translated_for_search.split() if len(w) > 3]
        q_vec = embedder.encode([translated_for_search])
        k = min(TOP_K, len(questions))
        dist, idxs = nn_model.kneighbors(q_vec, n_neighbors=k)

        candidates = []
        for rank, idx in enumerate(idxs[0]):
            emb_sim = 1 - dist[0][rank]
            keyword_match = any(
                keyword in questions[idx].lower() or keyword in answers[idx].lower()
                for keyword in keywords
            )
            if keyword_match and emb_sim >= COMBINED_THRESHOLD:
                candidates.append((emb_sim, answers[idx]))

        answer = candidates[0][1] if candidates else "لم أجد إجابة مناسبة حالياً."

    # ---------------------------
    # 🔹 ترجمة الإجابة إلى لغة المستخدم
    # ---------------------------
    t4 = time.time()
    final_answer = answer
    if detected_lang.lower() != "arabic":
        try:
            model = genai.GenerativeModel("models/gemini-2.5-pro")
            prompt = (
                f"Translate the following Arabic text to {detected_lang}. "
                "Reply ONLY with the translated text, no explanations:\n\n"
                f"{answer}"
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

    # ---------------------------
    # 💾 الحفظ في قاعدة البيانات
    # ---------------------------
    t5 = time.time()
    try:
        save_or_update_qa(translated_for_search, answer)
    except Exception as e:
        print("⚠️ فشل أثناء الحفظ:", e)
    return final_answer
# --------------------------------------------
# 📤 رفع قاعدة الأسئلة والأجوبة لبوستمان (upload_faq)
# --------------------------------------------
FAQ_PATH = "faq_data.json"

def initialize_memory():
    # هنا تقدرِ تحطي الكود اللي بيبني الفهرس أو الذاكرة
    print("✅ تم بناء الفهرس بنجاح.")

@app.route("/upload_faq", methods=["GET", "POST"])
def upload_faq():
    # ✅ لو المستخدم فتح الرابط في المتصفح (GET)
    if request.method == "GET":
        if os.path.exists(FAQ_PATH):
            with open(FAQ_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # نرجع JSON بشكل منسق
            return jsonify(data)
        else:
            return jsonify({"message": "❌ لا يوجد بيانات بعد."}), 404

    # ✅ لو المستخدم رفع بيانات (POST)
    try:
        data = request.json
        if not data:
            return jsonify({"error": "لم يتم إرسال أي بيانات."}), 400
        if not isinstance(data, list):
            return jsonify({"error": "البيانات يجب أن تكون قائمة (list) من العناصر."}), 400

        with open(FAQ_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        initialize_memory()
        return jsonify({"message": f"✅ تم رفع وحفظ {len(data)} موضوع بنجاح."}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------
# 💬 واجهة الدردشة (API)
# --------------------------------------------
@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "")
    session_id = request.json.get("session_id", "default")
    reply = get_best_answer(user_input)
    pretty_log_question_answer(user_input, reply)
    return jsonify({"reply": reply})
def pretty_log_question_answer(user_input, reply):
    """طباعة منسقة للسؤال والإجابة في التيرمينال"""
    from bidi.algorithm import get_display
    import datetime, sys

    # تصحيح الاتجاه + تأكد من الترميز UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    q_disp = get_display(user_input)
    a_disp = get_display(reply)
    now = datetime.datetime.now().strftime("%H:%M:%S")

    # الطباعة النهائية بنفس شكل Logات Flutter
    print("\n" + "=" * 60)
    print(f"🕒 [{now}]")
    print(f"📩 [USER QUESTION]: {q_disp}")
    print(f"🤖 [BOT ANSWER]: {a_disp}")
    print("=" * 60 + "\n")
# --------------------------------------------
# 🚀 تشغيل الخادم
# --------------------------------------------
if __name__ == "__main__":
    app.run(port=5000, debug=True)
