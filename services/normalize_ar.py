import re
from .remove_diacritics import remove_diacritics


def normalize_ar(text):
    t = text.lower()
    t = remove_diacritics(t)
    # حافظ على الحروف العربية والمناطق والفراغات، وكذلك الأرقام الغربية (0-9)،
    # الأرقام العربية-الهندية (٠-٩) والنقطة العربية "٫" والنقطة الغربية "."
    t = re.sub(r'[^\u0600-\u06FF\s0-9٠١٢٣٤٥٦٧٨٩\.٫]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()
