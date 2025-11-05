from flask import Blueprint, Flask, request, jsonify, current_app
import os
import json
# adjust imports to use local helpers (keep working import style)
try:
    # when running as module inside package, import from services
    from services.user_info_manager import load_user_data, save_user_data
except Exception:
    from user_info_manager import load_user_data, save_user_data

auth_bp = Blueprint("auth_receiver", __name__)

BASE_DIR = os.path.dirname(__file__)
SAVE_ADDRESS_PATH = os.path.join(BASE_DIR, "SaveAddrease.json")
USER_DATA_PATH = os.path.join(BASE_DIR, "user_data.json")


@auth_bp.route("/save_auth", methods=["POST"])
def save_auth():
    data = {}
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}
    # قبول مفتاح Authorization سواء بصيغة داخل الـ JSON أو كرأس في الطلب
    auth = data.get("Authorization") or data.get("authorization") or request.headers.get("Authorization") or request.headers.get("authorization")
    # قراءة contactId (يأتي من Flutter كـ contactId / crmUserId)
    contact_id = data.get("contactId") or data.get("contactid") or data.get("contactID")
    # تحويل نصي رقمي إلى int إن أمكن
    if isinstance(contact_id, str) and contact_id.isdigit():
        try:
            contact_id = int(contact_id)
        except Exception:
            pass

    # إذا لم يوجد auth أو هو None -> خطأ
    if auth is None:
        return jsonify({"error": "missing Authorization"}), 400

    # تنظيف القيمة: تحويل لأن تكون نصية، إزالة فراغات واقتباسات محيطة (إن وُجدت)
    auth = str(auth).strip()
    if len(auth) >= 2 and ((auth[0] == '"' and auth[-1] == '"') or (auth[0] == "'" and auth[-1] == "'")):
        auth = auth[1:-1].strip()

    # بعد التنظيف، إذا أصبحت السلسلة فارغة -> رفض (لا نخزن "")
    if auth == "":
        return jsonify({"error": "empty Authorization value"}), 400

    # تأكد أن القيمة مخزنة بصيغة كاملة "bearer <token>"
    if not auth.lower().startswith("bearer "):
        bearer_value = "bearer " + auth
    else:
        bearer_value = auth

    # 1) Save bearer token into user_data.json as auth_token (store WITH "bearer " prefix)
    try:
        user_data = load_user_data()
        if not isinstance(user_data, dict):
            user_data = {}
        user_data["auth_token"] = bearer_value
        # إذا أرسل contact_id/contactId نحدث user_data أيضًا ليتوافق مع SaveAddrease.json
        try:
            if contact_id is not None and str(contact_id).strip() != "":
                user_data["contactId"] = contact_id
                user_data["contact_id"] = contact_id
        except Exception:
            pass
        save_user_data(user_data)
    except Exception:
        # continue even if save fails
        pass

    # 2) Update SaveAddrease.json headers.Authorization (merge, atomic write) with bearer_value
    try:
        if os.path.exists(SAVE_ADDRESS_PATH):
            with open(SAVE_ADDRESS_PATH, "r", encoding="utf-8") as f:
                try:
                    payload = json.load(f)
                except Exception:
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
        else:
            payload = {}

        headers = payload.get("headers") or {}
        # فقط اكتب Authorization إذا كانت قيمة صالحة وغير فارغة
        if bearer_value and bearer_value.strip() != "":
            headers["Authorization"] = bearer_value
        payload["headers"] = headers

        # Ensure request section exists and set contactId when provided
        request_section = payload.get("request") or {}
        if contact_id is not None and str(contact_id).strip() != "":
            request_section["contactId"] = contact_id
        payload["request"] = request_section

        # atomic write
        tmp_path = SAVE_ADDRESS_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as tf:
            json.dump(payload, tf, ensure_ascii=False, indent=2)
        os.replace(tmp_path, SAVE_ADDRESS_PATH)

        try:
            current_app.logger.info("Saved bearer Authorization to SaveAddrease.json")
        except Exception:
            pass

    except Exception as e:
        return jsonify({"error": f"failed to update SaveAddrease.json: {e}"}), 500

    return jsonify({"status": "ok"}), 200


# allow running this file standalone for testing
if __name__ == "__main__":
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(auth_bp)
    # run on 0.0.0.0:5000 to match Android emulator 10.0.2.2
    app.run(host="0.0.0.0", port=5000)
