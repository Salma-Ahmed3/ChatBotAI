from flask import Flask, request, jsonify              
from sentence_transformers import SentenceTransformer  
from sklearn.neighbors import NearestNeighbors         
import google.generativeai as genai                    
import json, os, re, requests                         
from bs4 import BeautifulSoup                          
from bidi.algorithm import get_display                
from flask import send_from_directory                 
import time                                          

app = Flask(__name__)  


genai.configure(api_key="AIzaSyAD-40V_F3guIm58f8veagdoBwyN-b1M5I")
FAQ_PATH = os.path.join(os.path.dirname(__file__), "faq.json")
embedder = SentenceTransformer("all-MiniLM-L6-v2")
TOP_K = 5                
EMB_WEIGHT = 0.7           
TOKEN_WEIGHT = 0.3         
COMBINED_THRESHOLD = 0.60  


from keyWords import SERVICSE_KEYWORDS, ARABIC_STOPWORDS


def check_text_safety(text):
    """التحقق من سلامة النص باستخدام Gemini"""
    try:
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        prompt = f"""
        Analyze if this text contains any offensive content like:
        - Insults
        - Hate speech
        - Profanity
        - Threats
        - Inappropriate language
        
        Reply ONLY with "SAFE" or "UNSAFE". Nothing else.
        
        Text to analyze:
        {text}
        """
        
        resp = model.generate_content(prompt)
        result = resp.text.strip().upper()
        return result == "SAFE"
    except Exception as e:
        print("⚠️ خطأ في فحص سلامة النص:", e)
        return True 

questions, answers, token_sets = [], [], []   
nn_model = NearestNeighbors(n_neighbors=1, metric="cosine") 


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
    

    for topic in data:
        for qa in topic.get("questions", []):
            question = qa.get("question", "")
            answer_list = qa.get("answers", [])
            
            if question and answer_list:
                questions.append(question)
             
                answers.append("\n".join(answer_list))
                token_sets.append(tokens_from_text(question))
    
    if questions:
        build_index_from_memory()
        print(f"✅ تم تحميل {len(questions)} سؤال وبناء الفهرس بنجاح.")
    else:
        print("⚠️ لا توجد أسئلة محفوظة بعد.")

initialize_memory()
def save_or_update_qa(question, answer):
    data = load_faq_data()
    q_tokens = tokens_from_text(question)
    found_idx = None
    found_topic = None


    for topic in data:
        for qa in topic.get("questions", []):
            if token_overlap_score(q_tokens, tokens_from_text(qa["question"])) >= 0.6:
                found_topic = topic
                found_idx = data.index(topic)
                break
        if found_topic:
            break


    answer_list = answer.split("\n") if isinstance(answer, str) else answer

    if found_topic:

        for qa in found_topic["questions"]:
            if token_overlap_score(q_tokens, tokens_from_text(qa["question"])) >= 0.6:
                qa["answers"] = answer_list
                break
    else:

        new_topic = {
            "topic": extract_topic(question), 
            "questions": [{
                "question": question,
                "answers": answer_list
            }]
        }
        data.append(new_topic)

    with open(FAQ_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


    initialize_memory()

def extract_topic(question):
    """استخراج الموضوع من السؤال"""

    topic = question.replace("ما هي", "").replace("ما هو", "").replace("؟", "").strip()

    words = topic.split()[:3]
    return " ".join(words)

def filter_answers_by_query(user_text, data, min_token_len=4): 
    """
    فلترة عامة: إذا سألت عن شيء محدد، نعيد فقط الإجابات المتعلقة
    """
    tokens = [t for t in tokens_from_text(user_text) if len(t) >= min_token_len]
    if not tokens:
        return None

    matches = []
    required_matches = max(1, len(tokens)) 
    
    for topic in data:
        for qa in topic.get("questions", []):
            for ans in qa.get("answers", []):
                norm_ans = normalize_ar(ans)
                matched_tokens = 0
                
                for tok in tokens:
                    if tok in norm_ans:
                        matched_tokens += 1
                        if matched_tokens >= required_matches:
                            matches.append(ans)
                            break

      
            if matched_tokens < required_matches:
                norm_q = normalize_ar(qa.get("question", ""))
                for tok in tokens:
                    if tok in norm_q:
                        matched_tokens += 1
                        if matched_tokens >= required_matches:
                            matches.extend(qa.get("answers", []))
                            break

    if matches:
   
        unique_answers = list(dict.fromkeys(matches))[:2]
        return "\n".join(unique_answers)
    return None
API_URL = "https://b2c.mueen.com.sa:8021/api/content/Search/ar/mobileServicesSection?withchildren=true"

from bidi.algorithm import get_display

def fetch_services_from_api():
    try:
        print("🔍 جاري جلب الخدمات...")
        resp = requests.get(API_URL, timeout=10)
        print(f"حالة الاستجابة: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"خطأ في الاستجابة: {resp.text}")
            return "عذراً، حدث خطأ في جلب الخدمات. الرجاء المحاولة لاحقاً."
        
        data = resp.json()
        
        services = []
        # Handle the specific response structure
        for item in data:
            if item.get("children"):
                for child in item["children"]:
                    fields = child.get("fields", {})
                    title = fields.get("title", "").strip()
                    subtitle = fields.get("subTitle", "").strip()
                    
                    if title:
                        service_text = f"• {title}"
                        if subtitle:
                            service_text += f": {subtitle}"
                        services.append(service_text)
        
        if services:
            # Don't use get_display() here - let the client handle text direction
            result = "الخدمات المتوفرة:\n" + "\n".join(services)
            print("Final services list:", result)  # Debug print
            return result
        else:
            return "لم يتم العثور على خدمات متاحة."
            
    except requests.RequestException as e:
        print(f"⚠️ خطأ في الاتصال: {str(e)}")
        return "عذراً، حدث خطأ في الاتصال بالخدمة. الرجاء التأكد من اتصالك بالإنترنت والمحاولة لاحقاً."
    except Exception as e:
        print(f"⚠️ خطأ غير متوقع: {str(e)}")
        print("Response content:", resp.text)
        return "حدث خطأ أثناء جلب الخدمات، يرجى المحاولة لاحقاً."

def get_best_answer(user_input):
    # فحص سلامة النص أولاً
    if not check_text_safety(user_input):
        responses = {
            "ar": "عذراً، هذا أسلوب غير لائق. نرجو التحدث باحترام. شكراً لتفهمك 🚫",
            "en": "Sorry, this language is inappropriate. Please communicate respectfully. Thank you for understanding 🚫",
            "fr": "Désolé, ce langage est inapproprié. Veuillez communiquer respectueusement. Merci de votre compréhension 🚫",
            "es": "Lo siento, este lenguaje es inapropiado. Por favor, comuníquese respetuosamente. Gracias por su comprensión 🚫"
        }
    

    normalized_q = normalize_ar(user_input)

    # تحسين التحقق من الخدمات
    service_related = any(word in normalized_q for word in SERVICSE_KEYWORDS)
    if service_related:
        print(f"🔍 تم اكتشاف سؤال عن الخدمات: {user_input}")
        return fetch_services_from_api()

    original_text = user_input
    answer = ""


    t1 = time.time()
    model = genai.GenerativeModel("models/gemini-2.5-pro")
    try:
        resp = model.generate_content(
            f"""
            If the sender asks you for help, reply that you are here to help him.
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

 
        if any(word in detected_text.lower() for word in ["help", "مساعدتك", "aider", "ayudar", "aiutare"]):
            return detected_text  # الرد الترحيبي الجاهز من Gemini

        detected_lang = detected_text.split()[0].capitalize()

    except Exception as e:
        print("⚠️ فشل في تحديد اللغة أو الرد الترحيبي:", e)
        detected_lang = "Arabic"

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

 
    data = load_faq_data()
    normalized_q = normalize_ar(translated_for_search)

    filtered_answers = filter_answers_by_query(translated_for_search, data)
    if filtered_answers:
        if detected_lang.lower() != "arabic":
            try:
                model = genai.GenerativeModel("models/gemini-2.5-pro")
                prompt = (
                    f"Translate the following Arabic text to {detected_lang}. "
                    "Reply ONLY with the translated text, no explanations:\n\n"
                    f"{filtered_answers}"
                )
                resp = model.generate_content(prompt)
                clean_text = re.sub(
                    r"(?i)(here is the translation|of course|translation|sure|the answer is|Here is the English|:)",
                    "",
                    resp.text.strip()
                ).strip()
                return clean_text
            except Exception as e:
                print("⚠️ خطأ أثناء ترجمة الإجابات المفلترة:", e)
                return filtered_answers
        return filtered_answers

    if "حي" in normalized_q or "احياء" in normalized_q or "العناوين" in normalized_q:
        for topic in data:
            if normalize_ar(topic.get("topic", "")) == "العناوين":
  
                questions_list = topic.get("questions", [])
                if not questions_list:
                    break

   
                cities = questions_list[0].get("answers", [])
                city_text = " ".join(cities)
                cities_cleaned = [
                    c.strip().replace("،", "").replace(".", "")
                    for c in city_text.split()
                    if len(c.strip()) > 1
                ]

                for city in cities_cleaned:
                    if normalize_ar(city) in normalized_q:
            
                        for sub_topic in data:
                            if normalize_ar(sub_topic.get("topic", "")) == f"العناوين {normalize_ar(city)}":
                                areas = []
                                for q in sub_topic.get("questions", []):
                                    for ans in q.get("answers", []):
                                        areas.extend(ans.replace("،", ",").split(","))
                                areas = [a.strip() for a in areas if a.strip()]

        
                                for area in areas:
                                    if normalize_ar(area) in normalized_q:
                                        return f"نعم، حي {area} موجود ✅"

         
                                return (
                                    f"الحي المطلوب غير موجود في {city} ❌\n"
                                    f"هل ترغب أن أظهر لك الأحياء المتوفرة في {city}؟\n\n"
                                    "اكتب اسم المدينة الآن وسأعرضها لك 👇"
                                )


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

                return (
                    "الحي المطلوب غير موجود ❌\n"
                    "من فضلك اختر المدينة لمعرفة الأحياء المتوفرة فيها 👇\n\n"
                    "المدن المتاحة: الرياض، جدة، المدينة المنورة"
                )

    t3 = time.time()
    if not questions:
        answer = "لم أجد إجابة مناسبة حالياً. هل يمكنك توضيح سؤالك أكثر؟ او اذا اردت يمكنك التواصل مع خدمة العملاء لحل المشكلة ومراجعة سؤالك"
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

        answer = candidates[0][1] if candidates else "لم أجد إجابة مناسبة حالياً. هل يمكنك توضيح سؤالك أكثر؟ او اذا اردت يمكنك التواصل مع خدمة العملاء لحل المشكلة ومراجعة سؤالك."



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


    t5 = time.time()
    try:
        save_or_update_qa(translated_for_search, answer)
    except Exception as e:
        print("⚠️ فشل أثناء الحفظ:", e)
    return final_answer

FAQ_PATH = "faq_data.json"

def initialize_memory():

    print("✅ تم بناء الفهرس بنجاح.")

@app.route("/upload_faq", methods=["GET", "POST"])
def upload_faq():

    if request.method == "GET":
        if os.path.exists(FAQ_PATH):
            with open(FAQ_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # نرجع JSON بشكل منسق
            return jsonify(data)
        else:
            return jsonify({"message": "❌ لا يوجد بيانات بعد."}), 404


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


    sys.stdout.reconfigure(encoding="utf-8")
    q_disp = get_display(user_input)
    a_disp = get_display(reply)
    now = datetime.datetime.now().strftime("%H:%M:%S")


    print("\n" + "=" * 60)
    print(f"🕒 [{now}]")
    print(f"📩 [USER QUESTION]: {q_disp}")
    print(f"🤖 [BOT ANSWER]: {a_disp}")
    print("=" * 60 + "\n")

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')
# --------------------------------------------
# 🚀 تشغيل الخادم
# --------------------------------------------
if __name__ == "__main__":
    app.run(port=5000, debug=True)
