import json
import os

USER_REQUESTS_PATH = "data/user_requests.json"

def save_user_request(name, phone, address, district):
    """حفظ بيانات المستخدم اللي اختار (أخرى)"""
    user_data = {
        "name": name,
        "phone": phone,
        "address": address,
        "district": district
    }

    # لو الملف مش موجود، نعمله
    if not os.path.exists(USER_REQUESTS_PATH):
        with open(USER_REQUESTS_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=4)

    # نقرأ البيانات القديمة
    with open(USER_REQUESTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    data.append(user_data)

    # نكتب البيانات الجديدة
    with open(USER_REQUESTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return "✅ تم حفظ بياناتك بنجاح، شكراً لتعاونك!"
