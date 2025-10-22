import requests
from .fetch_services_from_api import SERVICE_API


def fetch_services_list():
    try:
        resp = requests.get(SERVICE_API, timeout=10)
        if resp.status_code != 200:
            return []

        data = resp.json()
        services = []

        for item in data:
            if item.get("children"):
                for child in item["children"]:
                    fields = child.get("fields", {})
                    title = fields.get("title", "").strip()
                    if title:
                        services.append(title)

        return services

    except Exception as e:
        print(f"خطأ أثناء جلب الخدمات: {str(e)}")
        return []
