import time
import re
import json
import os
import logging
import google.generativeai as genai
import requests

from typing import Any, Dict, List

from .check_text_safety import check_text_safety
from .normalize_ar import normalize_ar
from .tokens_from_text import tokens_from_text
from .filter_answers_by_query import filter_answers_by_query
from .fetch_services_from_api import (
    fetch_services_from_api,
    fetch_service_by_number,
    is_other_option,
)
from .state import QUESTIONS, ANSWERS, TOKEN_SETS, NN_MODEL, EMBEDDER, TOP_K, COMBINED_THRESHOLD
from .save_or_update_qa import save_or_update_qa
from keyWords import SERVICSE_KEYWORDS
from services.load_faq_data import load_faq_data
from .user_info_manager import (
    collect_user_info,
    update_user_info,
    load_user_data,
    save_user_data,
    create_lead_hourly,
)
from .user_info_manager import (
    fetch_housing_types,
    set_housing_selection,
)
from .save_fixed_package import (
    save_fixed_package,
    handle_nationality_selection,
    handle_shift_selection,
    get_available_shifts,
    get_available_nationalities,
    read_fixed_package,
    FIXED_PACKAGE_PATH,
)

LOGGER = logging.getLogger(__name__)
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

CITY_API = "https://erp.rnr.sa:8005/ar/api/city/ActiveCities"
CITYDISTRICT_API = "https://erp.rnr.sa:8005/ar/api/city/CityDistricts?cityId"
def get_best_answer(user_input):
    user_data = load_user_data()

    # نطبع نسخة مُطَبَّعة من السؤال مبكراً لاستخدامها في اكتشاف الخدمات
    normalized_q = normalize_ar(user_input)

    # -----------------------
    # معالجة اختيار نوع السكن عندما ننتظر هذا الحقل
    # -----------------------
    try:
        if user_data.get("pending_field") == "housing":
            ok, matched = set_housing_selection(user_input)
            if ok and matched:
                # إذا كان هناك إجراء معلق مثل 'services' نكمل كما كان بالسابق
                ud = load_user_data()
                ud["pending_field"] = "houseNo"
                save_user_data(ud)
                return f"✅ تم حفظ نوع المنزل: {matched.get('value')}\n\nالآن من فضلك أدخل رقم المنزل:"

            else:
                types = fetch_housing_types() or []
                if not types:
                    return "⚠️ حدث خطأ أثناء جلب أنواع السكن، حاول مرة أخرى لاحقاً."
                # عرض الخيارات للمستخدم لكتابتها بنفس الصيغة
                opts = " / ".join([t.get("value") for t in types])
                return f"لم أفهم نوع السكن الذي أدخلته. اختر واحداً من الأنواع التالية:\n{opts}"
    except Exception as e:
        print(f"⚠️ خطأ أثناء معالجة اختيار السكن: {e}")
        # 🔹 عندما يكون الحقل المطلوب رقم المنزل
    if user_data.get("pending_field") == "houseNo":
        update_user_info("houseNo", user_input)
        ud = load_user_data()
        ud["pending_field"] = "addressNotes"
        save_user_data(ud)
        return "تم حفظ رقم المنزل ✅\n\nالآن من فضلك أدخل أي تفاصيل إضافية عن العنوان (مثل مَعلم قريب أو وصف للمنزل):"

# 🔹 عندما يكون الحقل المطلوب ملاحظات العنوان
    if user_data.get("pending_field") == "addressNotes":
        update_user_info("addressNotes", user_input)
        ud = load_user_data()
        ud.pop("pending_field", None)
        save_user_data(ud)
    # حفظ اللقطة محلياً في SaveAddrease.json
        from .user_info_manager import save_address_snapshot
        save_address_snapshot(ud)
        # If we have a pending query (for example the user originally asked about services)
        # resume that question and return its ANSWER (not echo the user's question).
        prev_q = ud.get("pending_query")
        pending_action = ud.get("pending_action")
        if prev_q:
            # clear pending flags to avoid loops and mark that we're resuming the flow
            ud.pop("pending_action", None)
            ud.pop("pending_query", None)
            save_user_data(ud)

            try:
                # Call the same function to get the answer for the previous question.
                # This will run the normal QA/service logic and return the answer text.
                resumed_answer = get_best_answer(prev_q)
            except Exception as e:
                LOGGER.warning("⚠️ خطأ أثناء استئناف السؤال السابق: %s", e)
                resumed_answer = None

            if resumed_answer:
                return f"✅ تم حفظ تفاصيل العنوان بنجاح! يمكنك المتابعة الآن.\n\n{resumed_answer}"
            else:
                # If resuming failed, fall back to a polite confirmation message
                return "✅ تم حفظ تفاصيل العنوان بنجاح! يمكنك المتابعة الآن."

        # Fallback generic message if there's no pending query
        return "✅ تم حفظ تفاصيل العنوان بنجاح! يمكنك المتابعة الآن."

    # =====================
    # معالجة أسئلة عن الخدمات
     
    # أولاً: إذا المستخدم يسأل عن الخدمات، نتحقق هل لدينا بياناته كاملة
    service_related = any(word in normalized_q for word in SERVICSE_KEYWORDS)
    # إذا السؤال ليس عن الخدمات، جرب الإجابة من faq_data أولا
    if not service_related:
        try:
            data = load_faq_data()
            faq_answer = filter_answers_by_query(user_input, data)
            if faq_answer:
                return faq_answer
        except Exception as e:
            LOGGER.debug("⚠️ خطأ أثناء البحث في FAQ: %s", e)
        # لم نعثر على إجابة في FAQ لأسئلة غير متعلقة بالخدمات -> نطلب إيضاح من المستخدم
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
                        resp = requests.get(CITY_API, timeout=10)
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

                        url = f"{CITYDISTRICT_API}={city_id}"
                        resp = requests.get(url, timeout=10)
                        if resp.status_code == 200:
                            districts_data = resp.json().get("data", [])
                            matched_district = next((d for d in districts_data if d["value"].strip() == user_input.strip()), None)
                            if matched_district:
                                update_user_info("district", user_input.strip())
                                update_user_info("district_id", matched_district["key"])  # حفظ id الحي
                                # بعد حفظ الحي، سنطلب من المستخدم اختيار نوع المنزل (فيلا/عمارة)
                                try:
                                    types = fetch_housing_types()
                                    if not types:
                                        # لو لم تُرجع الأنواع، نكمل كما كان
                                        msg, next_field = collect_user_info()
                                        if msg:
                                            return msg
                                        ud = load_user_data()
                                        pending = ud.get("pending_action")
                                        if pending == "services":
                                            ud.pop("pending_action", None)
                                            ud.pop("pending_query", None)
                                            save_user_data(ud)
                                            services_text = fetch_services_from_api()
                                            return "✅ تم حفظ بياناتك بنجاح!\n\n" + services_text
                                        return "✅ تم حفظ بياناتك بنجاح! يمكنك المتابعة الآن."

                                    # حضِّر رسالة الخيارات للمستخدم
                                    opts = " / ".join([t.get("value") for t in types])
                                    ud = load_user_data()
                                    ud["pending_field"] = "housing"
                                    save_user_data(ud)
                                    return (
                                        "تم حفظ الحي بنجاح. الآن من فضلك أخبرني ما نوع المنزل: "
                                        f"\nالخيارات: {opts}\n"
                                        "اكتب اسم النوع كما هو (مثال: فيلا)"
                                    )
                                except Exception as e:
                                    print(f"⚠️ خطأ أثناء جلب أنواع السكن بعد حفظ الحي: {e}")
                                    msg, next_field = collect_user_info()
                                    if msg:
                                        return msg
                                    return "✅ تم حفظ بياناتك بنجاح! يمكنك المتابعة الآن."
                            else:
                                return f"❌ الحي '{user_input}' غير متوفر حالياً في مدينتك، سيتم إضافته قريباً بإذن الله الرجاء اختيار حي اخر."
                        else:
                            return "⚠️ حدث خطأ أثناء التحقق من الحي، حاول مرة أخرى لاحقاً."
                    except Exception as e:
                        print(f"⚠️ خطأ أثناء التحقق من الحي: {e}")
                        return "حدث خطأ أثناء الاتصال بخدمة الأحياء. حاول مرة أخرى لاحقاً."
                    # بعد حفظ الحي بنجاح، نحاول توليد إحداثيات افتراضية
                try:
                    city_name = user_data.get("city")
                    district_name = user_input.strip()
    
        # 🔹 مثال: توليد إحداثيات عشوائية ثابتة مؤقتاً (مكان API حقيقي لاحقاً)
                    import random
                    base_lat, base_lon = 24.7136, 46.6753  # مركز الرياض تقريباً
                    latitude = round(base_lat + random.uniform(-0.01, 0.01), 6)
                    longitude = round(base_lon + random.uniform(-0.01, 0.01), 6)
    
                    update_user_info("latitude", str(latitude))
                    update_user_info("longitude", str(longitude))

    # نحفظ اللقطة في SaveAddrease.json مباشرة
                    from .user_info_manager import save_address_snapshot
                    ud = load_user_data()
                    save_address_snapshot(ud)

                    print(f"✅ تم حفظ الإحداثيات: lat={latitude}, lon={longitude}")
                except Exception as e:
                    print(f"⚠️ فشل في توليد الإحداثيات: {e}")

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

    # التحقق من أن المدخل هو اختيار موعد (مثل A1 أو 1)
    shift_match = re.fullmatch(r"\s*([12]|[A-Za-z][12])\s*$", user_input)
    if shift_match:
        choice = user_input.strip()
        # نتأكد أن المستخدم اختار جنسية أولاً
        pkg = read_fixed_package()
        service_id = pkg.get("service_id")
        nationality_key = pkg.get("nationality_key")

        if service_id and nationality_key:
            # جلب المواعيد المتاحة
            try:
                shifts = get_available_shifts(service_id)
                if not shifts:
                    return "⚠️ لا توجد مواعيد متاحة لهذه الخدمة حالياً."
                return handle_shift_selection(choice, shifts)
            except Exception as exc:
                LOGGER.warning("⚠️ خطأ أثناء معالجة اختيار الموعد: %s", exc)
                return "⚠️ حدث خطأ أثناء معالجة اختيار الموعد. حاول مرة أخرى لاحقاً."

        # ليس لدينا خدمة أو جنسية محددة، نتعامل مع المدخل كاختيار خدمة عادي
        
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

    # حالة اختيار الجنسية بحرف واحد (A, B, ...)
    if re.fullmatch(r"\s*[A-Za-z]\s*$", user_input):
        choice = user_input.strip().upper()
        # نحاول تحميل الخدمة المختارة من FixedPackage.json
        pkg = read_fixed_package()
        service_id = pkg.get("service_id")
        if not service_id:
            return "⚠️ لا يوجد خدمة مختارة حالياً. من فضلك اختر خدمة أولاً ثم اختر الجنسية (A أو B)."

        # جلب الجنسيات المتاحة (يحاول من API أو من الملف المحلي)
        try:
            nationalities = get_available_nationalities(service_id)
        except Exception as exc:
            LOGGER.warning("⚠️ خطأ أثناء جلب الجنسيات: %s", exc)
            nationalities = None

        if not nationalities:
            return "⚠️ لا توجد جنسيات متاحة لهذه الخدمة حالياً أو حدث خطأ أثناء جلبها."

        # حفظ اختيار الجنسية وإرجاع رسالة تأكيد
        try:
            return handle_nationality_selection(choice, nationalities)
        except Exception as exc:
            LOGGER.warning("⚠️ خطأ أثناء حفظ اختيار الجنسية: %s", exc)
            return "⚠️ حدث خطأ أثناء معالجة اختيار الجنسية. حاول مرة أخرى لاحقاً."

    # حالة اختيار الموعد برقم (1 أو 2) أو بحرف+رقم (مثل A1)
    if re.fullmatch(r"\s*([12]|[A-Za-z][12])\s*$", user_input):
        choice = user_input.strip()
        pkg = read_fixed_package()
        service_id = pkg.get("service_id")
        nationality_key = pkg.get("nationality_key")

        if not service_id:
            return "⚠️ لا يوجد خدمة مختارة حالياً. من فضلك اختر خدمة أولاً."

        if not nationality_key:
            return "⚠️ لم يتم اختيار الجنسية بعد. من فضلك اختر الجنسية أولاً (A أو B)."

        # جلب المواعيد المتاحة
        try:
            shifts = get_available_shifts(service_id)
            if not shifts:
                return "⚠️ لا توجد مواعيد متاحة لهذه الخدمة حالياً."
            return handle_shift_selection(choice, shifts)
        except Exception as exc:
            LOGGER.warning("⚠️ خطأ أثناء معالجة اختيار الموعد: %s", exc)
            return "⚠️ حدث خطأ أثناء معالجة اختيار الموعد. حاول مرة أخرى لاحقاً."

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




