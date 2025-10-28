import json
import os
import requests
import uuid
USER_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "user_data.json")
HOURLYLEAD_API = "https://erp.rnr.sa:8005/ar/api/Lead/CreateHourly"

def load_user_data():
    """تحميل بيانات المستخدم من الملف"""
    if os.path.exists(USER_DATA_PATH):
        with open(USER_DATA_PATH, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_user_data(data):
    """حفظ بيانات المستخدم في ملف JSON"""
    with open(USER_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def collect_user_info():
    """
    تتحقق من وجود بيانات المستخدم (الاسم، رقم الهاتف، المدينة، الحي)
    ولو ناقصة ترجع النص المناسب لتسأل المستخدم عنها.
    """
    user_data = load_user_data()
    required_fields = {
        "name": "من فضلك أدخل اسمك الكامل:",
        "phone": "من فضلك أدخل رقم هاتفك:",
        "city": "من فضلك أدخل اسم مدينتك:",
        "district": "من فضلك أدخل اسم الحي:"
    }

    missing_fields = [key for key in required_fields if not user_data.get(key)]

    if missing_fields:
        next_field = missing_fields[0]
        return required_fields[next_field], next_field  # الرسالة + المفتاح المطلوب
    else:
        return None, None  # كل البيانات متوفرة

def update_user_info(field, value):
    """تحديث حقل معين في بيانات المستخدم"""
    user_data = load_user_data()
    # Normalize and save
    v = value.strip()
    if field == "phone":
        trans = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        v = v.translate(trans)
    user_data[field] = v
    if field == "phone":
        if not user_data.get("contactId") and not user_data.get("contact_id"):
            new_id = str(uuid.uuid4())
            user_data["contactId"] = new_id
            user_data["contact_id"] = new_id

    save_user_data(user_data)


def create_lead_hourly(pending_query=None, description=None):
    """ارسال بيانات المستخدم إلى API الخاص بإنشاء Lead بنظام hourly.
    ترجع (ok, response_message, sent_body).
    """
    try:
        user_data = load_user_data()

        url = HOURLYLEAD_API

        body = {
            "description": description or f"طلب وارد من البوت (خيار: {pending_query})",
            # بعض الحقول قد لا تكون متوفرة في ملف user_data لذا نبحث بعدة مفاتيح
            "contactId": user_data.get("contactId") or user_data.get("contact_id") or None,
            "cityId": user_data.get("city_id") or user_data.get("cityId") or None,
            "contactName": user_data.get("name"),
            "phoneNumber": user_data.get("phone"),
            "districtId": user_data.get("district_id") or user_data.get("districtId") or None,
            "serviceId": None,
        }

        headers = {"Content-Type": "application/json"}

        resp = requests.post(url, json=body, headers=headers, timeout=15)

        try:
            j = resp.json()
        except Exception:
            j = None

        if resp.status_code == 200:
            # مسح الحالة المعلقة لأن الطلب تم إرساله بنجاح
            if user_data.get("pending_action"):
                user_data.pop("pending_action", None)
            if user_data.get("pending_query"):
                user_data.pop("pending_query", None)
            save_user_data(user_data)

            resp_msg = None
            if isinstance(j, dict) and j.get("data"):
                resp_msg = str(j.get("data"))


            return True, resp_msg, body
        else:
            # لا نمسح الحالة المعلقة حتى يتم المحاولة لاحقاً
            msg = f"فشل إرسال الطلب، رمز الحالة: {resp.status_code}"
            if j and isinstance(j, dict) and j.get("message"):
                msg += f" - {j.get('message')}"
            return False, msg, body

    except Exception as e:
        return False, f"حدث خطأ أثناء إرسال الطلب: {e}", None
