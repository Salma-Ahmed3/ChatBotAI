from .fetch_services_list import fetch_services_list


def get_service_by_number(number):
    services = fetch_services_list()
    if not services:
        return "لم يتم العثور على خدمات متاحة."

    if 1 <= number <= len(services):
        return services[number - 1]
    else:
        return "الرقم الذي اخترته غير صالح."
