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
from .user_info_manager import collect_user_info, update_user_info, load_user_data, save_user_data, create_lead_hourly
import json
import requests

def get_best_answer(user_input):
    user_data = load_user_data()

    # نطبع نسخة مُطَبَّعة من السؤال مبكراً لاستخدامها في اكتشاف الخدمات
    normalized_q = normalize_ar(user_input)

    # أولاً: إذا المستخدم يسأل عن الخدمات، نتحقق هل لدينا بياناته كاملة
    service_related = any(word in normalized_q for word in SERVICSE_KEYWORDS)
    if service_related:
        print(f"🔍 تم اكتشاف سؤال عن الخدمات: {user_input}")
        # لو بيانات المستخدم ناقصة، نسجل أن هناك إجراء معلق ثم نطلب البيانات المطلوبة
        missing = [f for f in ["name", "phone", "city", "district"] if not user_data.get(f)]
        if missing:
            # حفظ الإجراء المعلق حتى يتم ارسال البيانات
            update_user_info("pending_action", "services")
            update_user_info("pending_query", user_input)
            # رسالة تمهيدية قبل طلب الحقل الأول
            initial_msg = "لِلإجابة عن سؤالك سوف نطلب منك بعض البيانات لإدخالها. لنقم بمتابعة طلبك:"
            msg, next_field = collect_user_info()
            if msg:
                # نعرض الرسالة التمهيدية متبوعة بسؤال الحقل المطلوب
                return initial_msg + "\n\n" + msg
        # لو البيانات كاملة، نرجع قائمة الخدمات مباشرة
        return fetch_services_from_api()

    # =====================
    # تأكيد المستخدم للطلب عندما يظهر له نص المتابعة "سوف نقوم الان..." ويكتب نعم/لا
    # =====================
    try:
        ud = load_user_data()
        pending = ud.get("pending_action")
        normalized_yes = re.fullmatch(r"\s*(نعم|yes)\s*[\.?؟!]*\s*$", normalized_q, flags=re.IGNORECASE)
        normalized_no = re.fullmatch(r"\s*(لا|no)\s*[\.?؟!]*\s*$", normalized_q, flags=re.IGNORECASE)

        if pending == "services" and (normalized_yes or normalized_no):
            # user confirmed
            if normalized_yes:
                # تأكد من توفر البيانات المطلوبة
                missing = [f for f in ["name", "phone", "city", "district"] if not ud.get(f)]
                if missing:
                    msg, next_field = collect_user_info()
                    if msg:
                        return msg

                # الآن جميع البيانات متوفرة، أرسل الطلب
                ok, resp_msg, sent_body = create_lead_hourly(pending_query=ud.get("pending_query"))
                if ok:
                    pretty = json.dumps(sent_body, ensure_ascii=False, indent=2)
                    return f"✅ تم إرسال الطلب بنجاح!"
                else:
                    return f"⚠️ فشل إرسال الطلب: {resp_msg}\n\nسنحتفظ بطلبك لمحاولة الإرسال لاحقاً."

            # user canceled
            if normalized_no:
                ud.pop("pending_action", None)
                ud.pop("pending_query", None)
                save_user_data(ud)
                return "✅ تم إلغاء إنشاء الطلب حسب طلبك. إذا رغبت في خدمات أخرى أبلغني." 
    except Exception as e:
        print(f"⚠️ خطأ أثناء معالجة تأكيد الطلب: {e}")

    if not check_text_safety(user_input):
        responses = {
            "ar": "عذراً، هذا أسلوب غير لائق. نرجو التحدث باحترام. شكراً لتفهمك 🚫",
            "en": "Sorry, this language is inappropriate. Please communicate respectfully. Thank you for understanding 🚫",
            "fr": "Désolé, ce langage est inapproprié. Veuillez communiquer respectueusement. Merci de votre compréhension 🚫",
            "es": "Lo siento, este lenguaje es inapropiado. Por favor, comuníquese respetuosamente. Gracias por su comprensión 🚫"
        }

    # إذا المستخدم يرسل بيانات مطلوبة (الاسم، الهاتف، المدينة، الحي) فنسجلها
    # لا نعتبر المرسل يسأل عن الحقل اذا كتب كلمات مثل 'اسم' أو 'رقم' أو 'مدينة' أو 'حي' (سؤال)
    for field in ["name", "phone", "city", "district"]:
        if not user_data.get(field):
            # تجاهل الإدخال إذا بدا أن المستخدم يطرح سؤالاً عن الحقل
            if len(user_input.strip().split()) >= 1 and not any(x in user_input for x in ["اسم", "رقم", "مدينة", "حي"]):

                # ✅ التحقق من المدينة
                if field == "city":
                    try:
                        resp = requests.get("https://erp.rnr.sa:8005/ar/api/city/ActiveCities", timeout=10)
                        if resp.status_code == 200:
                            cities_data = resp.json().get("data", [])
                            matched_city = next((c for c in cities_data if c["value"].strip() == user_input.strip()), None)
                            if matched_city:
                                update_user_info("city", user_input.strip())
                                update_user_info("city_id", matched_city["key"])  # حفظ id المدينة
                                msg, next_field = collect_user_info()
                                if msg:
                                    return msg  # يسأل المستخدم عن الحي الآن
                            else:
                                return f"❌ المدينة '{user_input}' غير متوفرة حالياً، سيتم توفيرها قريباً بإذن الله \n من فضلك قم باختيار مدينة اخرى لمتابعه انشاء الطلب."
                        else:
                            return "⚠️ حدث خطأ أثناء التحقق من المدينة، حاول مرة أخرى لاحقاً."
                    except Exception as e:
                        print(f"⚠️ خطأ أثناء التحقق من المدينة: {e}")
                        return "حدث خطأ أثناء الاتصال بخدمة المدن. حاول مرة أخرى لاحقاً."

                # ✅ التحقق من الحي بناءً على المدينة السابقة
                elif field == "district":
                    try:
                        city_id = user_data.get("city_id")
                        if not city_id:
                            return "⚠️ من فضلك أدخل اسم المدينة أولاً قبل الحي."

                        url = f"https://erp.rnr.sa:8005/ar/api/city/CityDistricts?cityId={city_id}"
                        resp = requests.get(url, timeout=10)
                        if resp.status_code == 200:
                            districts_data = resp.json().get("data", [])
                            matched_district = next((d for d in districts_data if d["value"].strip() == user_input.strip()), None)
                            if matched_district:
                                update_user_info("district", user_input.strip())
                                update_user_info("district_id", matched_district["key"])  # حفظ id الحي
                                msg, next_field = collect_user_info()
                                if msg:
                                    return msg
                                else:
                                    # بعد اكتمال البيانات بالكامل
                                    ud = load_user_data()
                                    pending = ud.get("pending_action")
                                    if pending == "services":
                                        ud.pop("pending_action", None)
                                        ud.pop("pending_query", None)
                                        save_user_data(ud)
                                        services_text = fetch_services_from_api()
                                        return "✅ تم حفظ بياناتك بنجاح!\n\n" + services_text
                                    return "✅ تم حفظ بياناتك بنجاح! يمكنك المتابعة الآن."
                            else:
                                return f"❌ الحي '{user_input}' غير متوفر حالياً في مدينتك، سيتم إضافته قريباً بإذن الله الرجاء اختيار حي اخر."
                        else:
                            return "⚠️ حدث خطأ أثناء التحقق من الحي، حاول مرة أخرى لاحقاً."
                    except Exception as e:
                        print(f"⚠️ خطأ أثناء التحقق من الحي: {e}")
                        return "حدث خطأ أثناء الاتصال بخدمة الأحياء. حاول مرة أخرى لاحقاً."

                # 🔹 الحقول العادية (الاسم، الهاتف)
                else:
                    update_user_info(field, user_input)
                    msg, next_field = collect_user_info()
                    if msg:
                        return msg
                    else:
                        ud = load_user_data()
                        pending = ud.get("pending_action")
                        if pending == "services":
                            ud.pop("pending_action", None)
                            ud.pop("pending_query", None)
                            save_user_data(ud)
                            services_text = fetch_services_from_api()
                            return "✅ تم حفظ بياناتك بنجاح!\n\n" + services_text
                        return "✅ تم حفظ بياناتك بنجاح! يمكنك المتابعة الآن."

            # إذا كتب المستخدم شيئًا يبدو كسؤال عن الحقل (مثل 'ما اسمك؟')، نتجاهل هذا الجزء من التخزين

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
            return "هل تقصد اختيار خدمة من القائمة؟ اكتب 'خدمات' أولاً."

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

    # if "حي" in normalized_q or "احياء" in normalized_q or "العناوين" in normalized_q:
    #     for topic in data:
    #         if normalize_ar(topic.get("topic", "")) == "العناوين":
    #             questions_list = topic.get("questions", [])
    #             if not questions_list:
    #                 break

    #             cities = questions_list[0].get("answers", [])
    #             city_text = " ".join(cities)
    #             cities_cleaned = [
    #                 c.strip().replace("،", "").replace(".", "")
    #                 for c in city_text.split()
    #                 if len(c.strip()) > 1
    #             ]

    #             for city in cities_cleaned:
    #                 if normalize_ar(city) in normalized_q:
    #                     for sub_topic in data:
    #                         if normalize_ar(sub_topic.get("topic", "")) == f"العناوين {normalize_ar(city)}":
    #                             areas = []
    #                             for q in sub_topic.get("questions", []):
    #                                 for ans in q.get("answers", []):
    #                                     areas.extend(ans.replace("،", ",").split(","))
    #                             areas = [a.strip() for a in areas if a.strip()]

    #                             for area in areas:
    #                                 if normalize_ar(area) in normalized_q:
    #                                     return f"نعم، حي {area} موجود ✅"

    #                             return (
    #                                 f"الحي المطلوب غير موجود في {city} ❌\n"
    #                                 f"هل ترغب أن أظهر لك الأحياء المتوفرة في {city}؟\n\n"
    #                                 "اكتب اسم المدينة الآن وسأعرضها لك 👇"
    #                             )

    #             all_areas = []
    #             for sub_topic in data:
    #                 if normalize_ar(sub_topic.get("topic", "")).startswith("العناوين"):
    #                     for q in sub_topic.get("questions", []):
    #                         for ans in q.get("answers", []):
    #                             all_areas.extend(ans.replace("،", ",").split(","))
    #             all_areas = [a.strip() for a in all_areas if a.strip()]

    #             for area in all_areas:
    #                 if normalize_ar(area) in normalized_q:
    #                     return f"نعم، حي {area} موجود ✅"

    #             return (
    #                 "الحي المطلوب غير موجود ❌\n"
    #                 "من فضلك اختر المدينة لمعرفة الأحياء المتوفرة فيها 👇\n\n"
    #                 "المدن المتاحة: الرياض، جدة، المدينة المنورة"
    #             )

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
    # 🟩 في النهاية، بعد توليد الإجابة، نتحقق من بيانات المستخدم
    msg, next_field = collect_user_info()
    if msg:
        # نضيف سؤال البيانات بعد الإجابة الأصلية
        return f"{final_answer}\n\n📋 {msg}"
    else:
        return final_answer




