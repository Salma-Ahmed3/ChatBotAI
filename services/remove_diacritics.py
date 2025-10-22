import re

def remove_diacritics(text):
    return re.sub(r'[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED]', '', text)
