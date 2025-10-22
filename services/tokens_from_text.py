from .normalize_ar import normalize_ar
from keyWords import ARABIC_STOPWORDS


def tokens_from_text(text):
    t = normalize_ar(text)
    return [w for w in t.split() if w and w not in ARABIC_STOPWORDS]
