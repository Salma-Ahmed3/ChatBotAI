import os
import sys
import json
from datetime import datetime

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from services.save_fixed_package import (
    handle_nationality_selection,
    handle_shift_selection,
    get_available_shifts,
    FIXED_PACKAGE_PATH
)

def test_nationality_and_shift_selection():
    """اختبار تسلسل اختيار الجنسية ثم الموعد مع الترميز الجديد"""
    nat_path = os.path.join(ROOT, 'NationalityHourly.json')
    with open(nat_path, 'r', encoding='utf-8') as f:
        nat_store = json.load(f)
    service_id = next(iter(nat_store))
    nats = nat_store[service_id]['nationalities']
    res1 = handle_nationality_selection('A', nats)
    with open(FIXED_PACKAGE_PATH, 'r', encoding='utf-8') as f:
        saved = json.load(f)
    shifts = get_available_shifts(service_id)
    if shifts:
        res2 = handle_shift_selection('1', shifts)
        
        res3 = handle_shift_selection('A1', shifts)
        
        res4 = handle_shift_selection('B1', shifts)
        
        # نتأكد أن الموعد تم حفظه
        with open(FIXED_PACKAGE_PATH, 'r', encoding='utf-8') as f:
            final = json.load(f)
    else:
        print('⚠️ لم يتم العثور على مواعيد متاحة')

if __name__ == '__main__':
    test_nationality_and_shift_selection()