"""Utilities to save selected service, nationality and shift into FixedPackage.json

This module refactors the previous single-file implementation by centralizing
file I/O, removing duplicated nationality-letter resolution logic, and keeping
the original Arabic messages and function signatures.
"""

from typing import Any, Dict, List, Optional
import json
import os
import time
import requests
import logging

LOGGER = logging.getLogger(__name__)
LOG_FMT = "%(levelname)s: %(message)s"
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format=LOG_FMT)


def _normalize_arabic_digits(s: str) -> str:
    """Normalize Arabic-Indic and Eastern Arabic-Indic digits to ASCII digits.

    This ensures inputs like '1', '١' (U+0661) or '۱' (U+06F1) are treated the same.
    """
    if not isinstance(s, str):
        return s
    trans = {chr(0x0660 + i): str(i) for i in range(10)}
    trans.update({chr(0x06F0 + i): str(i) for i in range(10)})
    return s.translate(str.maketrans(trans))


FIXED_PACKAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "FixedPackage.json")
RESOURCEGROUPS_API = "https://erp.rnr.sa:8005/ar/api/ResourceGroup/GetResourceGroupsByService?serviceId={}"


def _read_json_file(path: str) -> Optional[Dict[str, Any]]:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
    except Exception as exc:
        LOGGER.warning("⚠️ خطأ في قراءة الملف %s: %s", path, exc)
        return None


def _write_json_file(path: str, data: Dict[str, Any]) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:
        LOGGER.warning("⚠️ خطأ في حفظ الملف %s: %s", path, exc)
        return False


def read_fixed_package() -> Dict[str, Any]:
    """Return the contents of FixedPackage.json or an empty dict if missing."""
    data = _read_json_file(FIXED_PACKAGE_PATH)
    return data or {}


def write_fixed_package(updates: Dict[str, Any]) -> bool:
    """Update FixedPackage.json with given fields (merge with existing)."""
    pkg = read_fixed_package()
    pkg.update(updates)
    if _write_json_file(FIXED_PACKAGE_PATH, pkg):
        LOGGER.info("✅ تم حفظ البيانات في %s", FIXED_PACKAGE_PATH)
        return True
    return False


def save_nationality_to_package(nationality_key: Any, nationality_value: Any) -> bool:
    """تحديث ملف FixedPackage.json لإضافة الجنسية المختارة"""
    return write_fixed_package({"nationality_key": nationality_key, "nationality_value": nationality_value})


def save_shift_to_package(shift_key: Any, shift_value: Any) -> bool:
    """تحديث ملف FixedPackage.json لإضافة الموعد المختار"""
    return write_fixed_package({"shift_key": shift_key, "shift_value": shift_value})


def save_fixed_package(service_data: Dict[str, Any]) -> Any:
    """حفظ بيانات الخدمة المختارة في ملف FixedPackage.json

    Returns either the formatted nationalities message (if any found) or True on success.
    """
    try:
        # keep any stepId provided by the service data (some APIs return this)
        step_id = service_data.get("stepId") or service_data.get("step_id") or service_data.get("step")

        package_data = {
            "service_id": service_data.get("id"),
            "service_name": service_data.get("name"),
            "selected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        if step_id is not None:
            # persist canonical key "stepId" so later calls include it
            package_data["stepId"] = step_id

        if not write_fixed_package(package_data):
            return False

        # بعد حفظ الخدمة، نجلب الجنسيات المتاحة
        nationalities = get_available_nationalities(service_data.get("id"))
        if nationalities:
            return format_nationalities_message(nationalities)
        return True
    except Exception as exc:
        LOGGER.warning("⚠️ خطأ في حفظ الخدمة المختارة: %s", exc)
        return False


def get_available_nationalities(service_id: Any) -> Optional[List[Dict[str, Any]]]:
    """جلب الجنسيات المتاحة للخدمة from remote API.

    Returns list of nationality dicts or None on error/no-data.
    """
    try:
        url = RESOURCEGROUPS_API.format(service_id)
        LOGGER.info("📡 جلب الجنسيات المتاحة للخدمة %s", service_id)
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json().get("data", [])
        LOGGER.warning("⚠️ خطأ في جلب الجنسيات: %s", response.status_code)
        return None
    except Exception as exc:
        LOGGER.warning("⚠️ خطأ في جلب الجنسيات: %s", exc)
        return None


def format_nationalities_message(nationalities: List[Dict[str, Any]]) -> str:
    """تنسيق رسالة عرض الجنسيات المتاحة"""
    if not nationalities:
        return "⚠️ عذراً، لا توجد جنسيات متاحة لهذه الخدمة حالياً."

    options = []
    for i, nat in enumerate(nationalities):
        letter = chr(65 + i)  # A, B, C...
        value = nat.get("value", "غير معروف")
        options.append(f"{letter}- {value}")

    message = "من فضلك اختر الجنسية المطلوبة للحصول على الباقات:\n\n" + "\n".join(options)
    return message


def _resolve_nationality_letter(service_id: Any, nationality_value: str) -> Optional[str]:
    """Return the letter (A, B, ...) corresponding to the selected nationality value.

    This centralizes the remote fetch and index lookup used in several places.
    """
    try:
        nationalities = get_available_nationalities(service_id)
        if not nationalities:
            return None
        for i, nat in enumerate(nationalities):
            if nat.get("value") == nationality_value:
                return chr(65 + i)
    except Exception:
        return None
    return None


def get_available_shifts(service_id: Any) -> Optional[List[Dict[str, Any]]]:
    """جلب المواعيد المتاحة للخدمة من الملف المحلي"""
    shifts_path = os.path.join(os.path.dirname(__file__), "..", "HourlyServicesShift.json")
    try:
        data = _read_json_file(shifts_path)
        if not data:
            return None
        # try both str and raw key lookups to be forgiving to JSON keys
        service_shifts = data.get(service_id) or data.get(str(service_id)) or {}
        return service_shifts.get("shifts", [])
    except Exception as exc:
        LOGGER.warning("⚠️ خطأ في جلب المواعيد: %s", exc)
        return None


def format_shifts_message(shifts: List[Dict[str, Any]]) -> str:
    """تنسيق رسالة عرض المواعيد المتاحة مع إضافة رمز الجنسية المختارة"""
    if not shifts:
        return "⚠️ عذراً، لا توجد مواعيد متاحة لهذه الخدمة حالياً."

    nationality_letter = None
    try:
        pkg = read_fixed_package()
        nationality_value = pkg.get("nationality_value")
        service_id = pkg.get("service_id")
        if nationality_value and service_id:
            nationality_letter = _resolve_nationality_letter(service_id, nationality_value)
    except Exception as exc:
        LOGGER.warning("⚠️ خطأ في قراءة الجنسية المختارة: %s", exc)

    options = []
    for shift in shifts:
        key = shift.get("key")
        value = shift.get("value", "غير معروف")
        if nationality_letter:
            options.append(f"{nationality_letter}{key}- {value}")
        else:
            options.append(f"{key}- {value}")

    message = "من فضلك اختر الموعد المناسب:\n\n" + "\n".join(options)
    return message


def handle_nationality_selection(choice: str, nationalities: List[Dict[str, Any]]) -> str:
    """معالجة اختيار الجنسية وحفظها"""
    try:
        choice = choice.upper().strip()
        if len(choice) != 1 or not "A" <= choice <= "Z":
            return "⚠️ اختيار غير صالح. الرجاء اختيار الحرف المناسب (مثل A أو B)"

        index = ord(choice) - ord("A")
        if index < 0 or index >= len(nationalities):
            return "⚠️ الجنسية المختارة غير موجودة في القائمة"

        selected_nationality = nationalities[index]
        nationality_key = selected_nationality.get("key")
        nationality_value = selected_nationality.get("value")

        if save_nationality_to_package(nationality_key, nationality_value):
            pkg = read_fixed_package()
            service_id = pkg.get("service_id")
            if service_id:
                shifts = get_available_shifts(service_id)
                if shifts:
                    shift_msg = format_shifts_message(shifts)
                    return f"✅ تم اختيار الجنسية: {nationality_value}\n\n{shift_msg}"
            return f"✅ تم اختيار الجنسية: {nationality_value}"
        else:
            return "⚠️ حدث خطأ في حفظ الجنسية المختارة"
    except Exception as exc:
        LOGGER.warning("⚠️ خطأ في معالجة اختيار الجنسية: %s", exc)
        return "⚠️ حدث خطأ في معالجة اختيار الجنسية"




def handle_shift_selection(choice: str, shifts: List[Dict[str, Any]]) -> str:
    """معالجة اختيار الموعد وحفظه - يقبل الإدخال بشكل رقم فقط أو حرف+رقم مثل A1"""
    try:
        choice = choice.strip()
        pkg = read_fixed_package()
        nationality_value = pkg.get("nationality_value")
        service_id = pkg.get("service_id")
        nationality_letter = None
        if nationality_value and service_id:
            nationality_letter = _resolve_nationality_letter(service_id, nationality_value)

        # التعامل مع الإدخال سواء كان رقماً فقط أو حرف+رقم
        if len(choice) > 1 and choice[0].isalpha():
            input_letter = choice[0].upper()
            if nationality_letter and input_letter != nationality_letter:
                return f"⚠️ الحرف {input_letter} غير صحيح. الجنسية المختارة هي {nationality_letter}"
            try:
                shift_num = int(choice[1:])
            except ValueError:
                return "⚠️ اختيار غير صالح. الرجاء اختيار الموعد بالشكل الصحيح (مثل A1 أو 1)"
        else:
            try:
                shift_num = int(choice)
            except ValueError:
                return "⚠️ اختيار غير صالح. الرجاء اختيار الموعد بالشكل الصحيح (مثل A1 أو 1)"

        selected_shift = next((s for s in shifts if s.get("key") == shift_num), None)
        if not selected_shift:
            return "⚠️ الموعد المختار غير موجود في القائمة"

        shift_key = selected_shift.get("key")
        shift_value = selected_shift.get("value")

        if save_shift_to_package(shift_key, shift_value):
            # بعد حفظ الموعد: استدعاء API إضافة العنوان وطباعه النتيجة
            try:
                from .user_info_manager import load_user_data, save_address_snapshot

                user_data = load_user_data()
                result = save_address_snapshot(user_data)
                print(f"Called ADD_ADDRESS_API, result: {result}")
            except Exception as e:
                print(f"Error calling ADD_ADDRESS_API: {e}")
            return f"✅ تم اختيار الموعد: {shift_value}"
        else:
            return "⚠️ حدث خطأ في حفظ الموعد المختار"
    except Exception as exc:
        LOGGER.warning("⚠️ خطأ في معالجة اختيار الموعد: %s", exc)
        return "⚠️ حدث خطأ في معالجة اختيار الموعد"