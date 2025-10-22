import requests
from .state import FAQ_PATH

SERVICE_API = "https://erp.rnr.sa:8016/api/content/Search/ar/mobileServicesSection?withchildren=true"
SERVICES_DETAILS_API = "https://erp.rnr.sa:8005/ar/api/Service/ServicesForService?serviceType={}"
PROFESSIONGROUP_API = "https://api.mueen.com.sa/ar/api/ProfessionGroups/AvailableProfessions"

SERVICES_MAP = {}


def fetch_services_from_api():
    """جلب قائمة القطاعات الرئيسية"""
    try:
        print("🔍 جاري جلب القطاعات...")
        resp = requests.get(SERVICE_API, timeout=10)
        print(f"حالة الاستجابة: {resp.status_code}")

        if resp.status_code != 200:
            print(f"⚠️ خطأ في الاستجابة: {resp.text}")
            return "عذراً، حدث خطأ في جلب القطاعات. الرجاء المحاولة لاحقاً."

        data = resp.json()
        services = []
        counter = 1
        SERVICES_MAP.clear()

        for item in data:
            if item.get("children"):
                for child in item["children"]:
                    fields = child.get("fields", {})
                    title = fields.get("title", "").strip()
                    if title:
                        SERVICES_MAP[counter] = child
                        services.append(f"{counter}. {title}")
                        counter += 1

        if not services:
            return "⚠️ لم يتم العثور على قطاعات متاحة حالياً."

        result = (
            "لدينا العديد من الخدمات في قطاعات مختلفة، من فضلك اختر رقم القطاع لجلب الخدمات بداخله:\n\n"
            + "\n".join(services)
        )
        return result

    except Exception as e:
        print(f"⚠️ خطأ غير متوقع أثناء جلب القطاعات: {e}")
        return "حدث خطأ أثناء جلب القطاعات، يرجى المحاولة لاحقاً."


def fetch_service_by_number(number):
    """جلب الخدمات داخل القطاع المحدد حسب رقمه"""
    try:
        # دعم الأرقام العربية
        num_str = str(number).strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        idx = int(num_str)

        if not SERVICES_MAP:
            fetch_services_from_api()

        if not SERVICES_MAP:
            return "⚠️ لا توجد قطاعات متاحة حالياً."

        service = SERVICES_MAP.get(idx)
        if not service:
            return f"⚠️ الرقم {idx} غير متوفر. الرجاء اختيار رقم من الأرقام المعروضة."

        fields = service.get("fields", {})
        title = fields.get("title", "غير معروف").strip()

        #  لو الرقم 1 → نستخدم SERVICES_DETAILS_API (ساعات)
        if idx == 1:
            url = SERVICES_DETAILS_API.format(idx)
            print(f"📡 جلب بيانات القطاع 1 من {url}")
            resp = requests.get(url, timeout=10)

            if resp.status_code != 200:
                return "⚠️ حدث خطأ أثناء جلب خدمات هذا القطاع."

            data = resp.json().get("data", [])
            if not data:
                return f"❌ لا توجد خدمات متاحة في القطاع ({idx})."

            sub_services = []
            for i, item in enumerate(data, 1):
                name = item.get("name", "خدمة بدون اسم").strip()
                desc = item.get("description", "لا يوجد وصف").strip()
                sub_services.append(f"{i}. {name} : {desc}")

            #  إضافة خيار "أخرى" بعد آخر خدمة
            sub_services.append(f"{len(data) + 1}. أخرى")
   

            # حفظ رقم آخر خدمة (عشان نعرف ان المستخدم اختار اخرى)
            SERVICES_MAP["last_option_for_sector"] = {
            "sector_number": idx,
            "last_option_number": len(data) + 1
            }

            result = (
            f"الخدمات المتوفرة في قطاع ({idx}) - {title} هي:\n\n"
            + "\n".join(sub_services)
            + "\n\nمن فضلك اختر رقم الخدمة للحصول على المزيد من التفاصيل."
        )
            return result
        #  لو الرقم 2 → نستخدم PROFESSIONGROUP_API (افراد)
        
        if idx == 2:
            url = PROFESSIONGROUP_API.format(idx)
            print(f"📡 جلب بيانات القطاع 2 من {url}")
            resp = requests.get(url, timeout=10)

            if resp.status_code != 200:
                return "⚠️ حدث خطأ أثناء جلب خدمات هذا القطاع."

            data = resp.json().get("data", [])
            if not data:
                return f"❌ لا توجد خدمات متاحة في القطاع ({idx})."

            sub_services = []
            for i, item in enumerate(data, 1):
                name = item.get("value", "خدمة بدون اسم").strip()
                desc = item.get("description", "لا يوجد وصف").strip()
                sub_services.append(f"{i}. {name} : {desc}")

            #  إضافة خيار "أخرى" بعد آخر خدمة
            sub_services.append(f"{len(data) + 1}. أخرى")
   

            # حفظ رقم آخر خدمة (عشان نعرف ان المستخدم اختار اخرى)
            SERVICES_MAP["last_option_for_sector"] = {
            "sector_number": idx,
            "last_option_number": len(data) + 1
            }

            result = (
            f"الخدمات المتوفرة في قطاع ({idx}) - {title} هي:\n\n"
            + "\n".join(sub_services)
            + "\n\nمن فضلك اختر رقم الخدمة للحصول على المزيد من التفاصيل."
        )
            return result


        #  لو الرقم 3(صيانه)
        elif idx == 3:
            return "🔧 سوف يتم توفير خدمة الصيانة قريباً."
        # لو الرقم 4 (ليد وساطه)
        elif idx == 4:
                     return "🔧 سوف يتم توفير خدمة الوساطة قريباً."
        #  باقي الأرقام مستقبلاً نضيف لهم APIs أخرى هنا
        else:
            return f"ℹ️ القطاع رقم ({idx}) لم يتم ربطه بعد بأي مصدر بيانات."

    except Exception as e:
        print(f"⚠️ خطأ أثناء جلب تفاصيل القطاع: {e}")
        return "حدث خطأ أثناء جلب تفاصيل القطاع. حاول مرة أخرى لاحقاً."
def is_other_option(sector_number, chosen_number):
    """يتأكد إن المستخدم اختار (أخرى) الخاصة بالقطاع"""
    info = SERVICES_MAP.get("last_option_for_sector")
    if not info:
        return False
    return (
        info["sector_number"] == sector_number
        and info["last_option_number"] == chosen_number
    )
