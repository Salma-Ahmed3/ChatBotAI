import json
import os
import sys
from services.save_fixed_package import handle_nationality_selection

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
BASE = os.path.dirname(os.path.dirname(__file__))
FIXED = os.path.join(BASE, 'fixedPackage.json')
NAT_PATH = os.path.join(BASE, 'NationalityHourly.json')

with open(FIXED, 'r', encoding='utf-8') as f:
    fixed = json.load(f)
service_id = fixed.get('service_id')

with open(NAT_PATH, 'r', encoding='utf-8') as f:
    nat_store = json.load(f)

nats = nat_store.get(service_id, {}).get('nationalities', [])
print('Loaded nationalities count =', len(nats))

if not nats:
    print('No nationalities found for service', service_id)
else:
    # call handler with 'A'
    res = handle_nationality_selection('A', nats)
    with open(FIXED, 'r', encoding='utf-8') as f:
        after = json.load(f)

