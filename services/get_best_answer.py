import time
import re
import google.generativeai as genai
from .check_text_safety import check_text_safety
from .normalize_ar import normalize_ar
from .tokens_from_text import tokens_from_text
from .filter_answers_by_query import filter_answers_by_query
from .fetch_services_from_api import fetch_services_from_api
from .fetch_services_from_api import fetch_service_by_number
from .state import QUESTIONS, ANSWERS, TOKEN_SETS, NN_MODEL, EMBEDDER, TOP_K, COMBINED_THRESHOLD
from .save_or_update_qa import save_or_update_qa
from keyWords import SERVICSE_KEYWORDS
from services.load_faq_data import load_faq_data
from .fetch_services_from_api import is_other_option



def get_best_answer(user_input):
    if not check_text_safety(user_input):
        responses = {
            "ar": "عذراً، هذا أسلوب غير لائق. نرجو التحدث باحترام. شكراً لتفهمك 🚫",
            "en": "Sorry, this language is inappropriate. Please communicate respectfully. Thank you for understanding 🚫",
            "fr": "Désolé, ce langage est inapproprié. Veuillez communiquer respectueusement. Merci de votre compréhension 🚫",
            "es": "Lo siento, este lenguaje es inapropiado. Por favor, comuníquese respetuosamente. Gracias por su comprensión 🚫"
        }

    normalized_q = normalize_ar(user_input)

    service_related = any(word in normalized_q for word in SERVICSE_KEYWORDS)
    if service_related:
        print(f"🔍 تم اكتشاف سؤال عن الخدمات: {user_input}")
        return fetch_services_from_api()

    # If the user input is just a number (Arabic-Indic or Western numerals), treat it as a selection
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    normalized_digits = normalized_q.translate(trans).strip()
    # التعرف على اختيار رقمي أو بصيغة نقطية (مثل 1.2 أو ١.٢)
    # نحول الأرقام العربية ثم نعوض الفاصل العربي "٫" إلى نقطة
    normalized_digits = normalized_digits.replace("٫", ".").replace(",", ".").replace(" ", "")

    #  حالة الاختيار بصيغة نقطية
    if re.fullmatch(r"\d+\.\d+", normalized_digits):
        print(f"🔢 تم اكتشاف اختيار رقمي بنقطة للخدمة: {user_input}")
        # Only treat this as a service selection if we previously listed services
        from .fetch_services_from_api import SERVICES_MAP
        if not SERVICES_MAP:
            return (
                "هل تقصد اختيار خدمة؟ لعرض قائمة القطاعات اكتب 'خدمات' أو اسأل عن الخدمات أولاً، "
                "ثم اختر رقم القطاع لكي أتمكن من مساعدتك"
            )

        # نمرر السلسلة كما هي لـ fetch_service_from_api (التي تدعمها الآن)
        return fetch_service_by_number(normalized_digits)

    #  حالة الاختيار برقم واحد فقط
    if re.fullmatch(r"\d+", normalized_digits):
        print(f"🔢 تم اكتشاف اختيار رقمي للخدمة: {user_input}")
        num = int(normalized_digits)

        # تحديد القطاع الحالي (آخر قطاع المستخدم اختاره)
        # نجيبه من SERVICES_MAP لو مخزّن
        from .fetch_services_from_api import SERVICES_MAP
        # If we haven't shown services yet, asking a raw number shouldn't fetch data.
        if not SERVICES_MAP:
            return (
                "هل تقصد اختيار خدمة من القائمة؟ لعرض القطاعات المتاحة اكتب 'خدمات' أولاً أو وضّح طلبك وسأنصحك بالخطوة التالية."
            )

        info = SERVICES_MAP.get("last_option_for_sector")
        current_sector = info["sector_number"] if info else None

        # تحقق لو اختار "أخرى" (يتوقع is_other_option الشكل القطاعي والنقطة)
        if current_sector and is_other_option(current_sector, num):
            return "من فضلك أدخل اسمك ورقم هاتفك وعنوانك والحي ليتم حفظ بياناتك."

        # Otherwise return the service details for the chosen number
        return fetch_service_by_number(num)

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
            return detected_text

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
    if not QUESTIONS:
        answer = "لم أجد إجابة مناسبة حالياً. هل يمكنك توضيح سؤالك أكثر؟ او اذا اردت يمكنك التواصل مع خدمة العملاء لحل المشكلة ومراجعة سؤالك"
    else:
        keywords = [w.strip("؟,.،") for w in translated_for_search.split() if len(w) > 3]
        q_vec = EMBEDDER.encode([translated_for_search])
        k = min(TOP_K, len(QUESTIONS))
        dist, idxs = NN_MODEL.kneighbors(q_vec, n_neighbors=k)

        candidates = []
        for rank, idx in enumerate(idxs[0]):
            emb_sim = 1 - dist[0][rank]
            keyword_match = any(
                keyword in QUESTIONS[idx].lower() or keyword in ANSWERS[idx].lower()
                for keyword in keywords
            )
            if keyword_match and emb_sim >= COMBINED_THRESHOLD:
                candidates.append((emb_sim, ANSWERS[idx]))

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
