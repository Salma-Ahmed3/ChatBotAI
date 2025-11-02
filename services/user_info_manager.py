import json
import os
import requests
import uuid
import datetime
USER_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "user_data.json")
HOURLYLEAD_API = "https://erp.rnr.sa:8005/ar/api/Lead/CreateHourly"
ADD_ADDRESS_API = "https://erp.rnr.sa:8005/ar/api/HourlyContract/AddNewAddress"
HOUSING_API = "https://erp.rnr.sa:8005/ar/api/ContactAddress/HousingTypes"

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


def fetch_housing_types():
    """جلب أنواع السكن من الـ API (قائمة من كائنات {key, value})"""
    try:
        resp = requests.get(HOUSING_API, timeout=10)
        if resp.status_code == 200:
            j = resp.json()
            return j.get("data", [])
        return None
    except Exception:
        return None


def set_housing_selection(value):
    """حاول مطابقة قيمة نوع السكن (مثل 'فيلا' أو 'عمارة') مع بيانات الـ API وحفظ المفتاح والقيمة في user_data.
    ترجع tuple (ok: bool, matched_item_or_none)
    """
    user_data = load_user_data()
    if not value:
        return False, None
    v = value.strip()
    types = fetch_housing_types() or []
    matched = next((t for t in types if str(t.get("value", "")).strip() == v), None)
    if not matched:
        # حاول المطابقة بدون تشكيل أو بتحويل أرقام/فراغات
        matched = next((t for t in types if t.get("value", "").strip().lower() == v.lower()), None)

    if matched:
        # حفظ المفتاح والقيمة
        user_data["housing_key"] = matched.get("key")
        user_data["housing_value"] = matched.get("value")
        # علامة خاصة إذا كانت فيلا
        try:
            if str(matched.get("value", "")).strip() == "فيلا":
                user_data["is_villa"] = True
            else:
                user_data.pop("is_villa", None)
        except Exception:
            pass

        # إزالة أي حقل معلق متعلق بالسكن
        if user_data.get("pending_field") == "housing":
            user_data.pop("pending_field", None)

        save_user_data(user_data)

        # قم بحفظ لقطة محلية من بيانات العنوان في SaveAddrease.json حتى لو لم نرسل الطلب بعد
        try:
            save_address_snapshot(user_data)
        except Exception:
            # لا نمنع العملية إذا فشل الحفظ المحلي
            pass

        return True, matched

    return False, None


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


def add_new_address(hourlyServiceId: str, stepId: str):
    """Send address data (taken from user_data.json) to the AddNewAddress API.

    The URL format used by the API is:
      ADD_ADDRESS_API + "?hourlyServiceId={hourlyServiceId}&stepId={stepId}"

    The function will:
    - build the request body from available fields in user_data
    - POST to the API
    - save the same body into the user's data file
    - write a file SaveAddrease.json next to the project root containing the request and the API response

    Returns: (ok: bool, resp_json_or_message, sent_body_or_none)
    """
    try:
        user_data = load_user_data()

        contact_id = user_data.get("contactId") or user_data.get("contact_id")

        body = {
            "contactId": contact_id,
            "addressNotes": user_data.get("addressNotes") or user_data.get("address_notes") or "",
            "houseNo": user_data.get("houseNo") or user_data.get("house_no") or "",
            # houseType is expected as a key string/number - use saved housing_key if exists
            "houseType": str(user_data.get("housing_key")) if user_data.get("housing_key") is not None else (str(user_data.get("houseType")) if user_data.get("houseType") is not None else "0"),
            "floorNo": user_data.get("floorNo") or user_data.get("floor_no") or "0",
            "apartmentNo": user_data.get("apartmentNo") or user_data.get("apartment_no") or "0",
            "cityId": user_data.get("city_id") or user_data.get("cityId") or None,
            "districtId": user_data.get("district_id") or user_data.get("districtId") or None,
            "latitude": str(user_data.get("latitude") or ""),
            "longitude": str(user_data.get("longitude") or ""),
            # type in example is 2 (use same default)
            "type": 2,
        }

        # Persist these fields into user_data for future reference
        user_data.update({
            "addressNotes": body["addressNotes"],
            "houseNo": body["houseNo"],
            "houseType": body["houseType"],
            "floorNo": body["floorNo"],
            "apartmentNo": body["apartmentNo"],
        })
        save_user_data(user_data)

        # Build URL with query params
        url = f"{ADD_ADDRESS_API}?hourlyServiceId={hourlyServiceId}&stepId={stepId}"
        headers = {"Content-Type": "application/json"}

        resp = requests.post(url, json=body, headers=headers, timeout=15)

        try:
            resp_json = resp.json()
        except Exception:
            resp_json = {"status_text": resp.text}


        # Save request+response to SaveAddrease.json as valid JSON (url, body, response)
        save_path = os.path.join(os.path.dirname(__file__), "..", "SaveAddrease.json")
        try:
            snapshot = {
                "url": url,
                "body": body,
                "response": resp_json
            }
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
        except Exception as e:
            # If writing the file fails, continue but include warning in return message
            return False, f"تم إرسال الطلب لكن فشل حفظ SaveAddrease.json: {e}", body

        if resp.status_code == 200:
            return True, resp_json, body
        else:
            return False, resp_json, body

    except Exception as e:
        return False, f"حدث خطأ أثناء إرسال عنوان المستخدم: {e}", None


def save_address_snapshot(user_data: dict, resp_json=None, status_code=None):
    """Save a local snapshot file 'SaveAddrease.json' containing the address request body
    and optional response/status. This runs locally and does not require calling the API.
    """
    try:
        contact_id = user_data.get("contactId") or user_data.get("contact_id")

        body = {
            "contactId": contact_id,
            "addressNotes": user_data.get("addressNotes") or user_data.get("address_notes") or "",
            "houseNo": user_data.get("houseNo") or user_data.get("house_no") or "",
            "houseType": str(user_data.get("housing_key")) if user_data.get("housing_key") is not None else (str(user_data.get("houseType")) if user_data.get("houseType") is not None else "0"),
            "floorNo": user_data.get("floorNo") or user_data.get("floor_no") or "0",
            "apartmentNo": user_data.get("apartmentNo") or user_data.get("apartment_no") or "0",
            "cityId": user_data.get("city_id") or user_data.get("cityId") or None,
            "districtId": user_data.get("district_id") or user_data.get("districtId") or None,
            "latitude": str(user_data.get("latitude") or ""),
            "longitude": str(user_data.get("longitude") or ""),
            "type": 2,
        }

        save_path = os.path.join(os.path.dirname(__file__), "..", "SaveAddrease.json")
        payload = {
            "request": body,
            "response": resp_json,
            "status_code": status_code,
            "saved_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        # Return False but don't raise so callers can continue
        try:
            # best-effort: try to write an error file next to snapshot
            err_path = os.path.join(os.path.dirname(__file__), "..", "SaveAddrease_error.log")
            with open(err_path, "a", encoding="utf-8") as ef:
                ef.write(f"{datetime.datetime.utcnow().isoformat()} - save_address_snapshot error: {e}\n")
        except Exception:
            pass
        return False
