import json
import os

USER_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "user_data.json")

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
    user_data[field] = value.strip()
    save_user_data(user_data)
