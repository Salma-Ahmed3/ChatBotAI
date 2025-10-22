import re
from .remove_diacritics import remove_diacritics


def normalize_ar(text):
    t = text.lower()
    t = remove_diacritics(t)
    t = re.sub(r'[^\u0600-\u06FF\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()
