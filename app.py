# app.py — إصدار ذكي يطابق عدد الساعات بدقة في الأسئلة
from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import NearestNeighbors
import google.generativeai as genai
from langdetect import detect
import json, os, re, requests

app = Flask(__name__)
genai.configure(api_key="AIzaSyBEeidGnK_uyf9ikJWW9elsAgDdz8t09oA")

FAQ_PATH = os.path.join(os.path.dirname(__file__), "faq.json")
embedder = SentenceTransformer("all-MiniLM-L6-v2")

TOP_K = 5
EMB_WEIGHT = 0.7
TOKEN_WEIGHT = 0.3
COMBINED_THRESHOLD = 0.60

ARABIC_STOPWORDS = {
    "في","من","ما","هي","ماهي","ما هي","لم","عن","على","و","او","أو",
    "هل","كيف","أين","كم","هذا","هذه","ذلك","تكون","يكون","هو","هي","إلى","ب"
}

SERVICE_ENDPOINTS = {
    "resource_groups": "https://api.mueen.com.sa/ar/api/ResourceGroup/GetResourceGroupsByService?serviceId={serviceId}",
    "fixed_package": "https://api.mueen.com.sa/ar/api/HourlyContract/FixedPackage?stepId={stepId}&nationalityId={nationalityId}&shift={shift}"
}

questions, answers, token_sets = [], [], []
nn_model = NearestNeighbors(n_neighbors=1, metric="cosine")

# ==================== المساعدة ====================
def normalize_ar(text):
    t = (text or "").lower()
    t = re.sub(r'[^\u0600-\u06FF0-9\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

def tokens_from_text(text):
    return [w for w in normalize_ar(text).split() if w and w not in ARABIC_STOPWORDS]

def token_overlap_score(q_tokens, c_tokens):
    if not c_tokens:
        return 0.0
    return len(set(q_tokens) & set(c_tokens)) / max(len(c_tokens), 1)

def load_faq_data():
    if not os.path.exists(FAQ_PATH):
        return []
    with open(FAQ_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def build_index_from_memory():
    global nn_model
    if not questions:
        return
    embeddings = embedder.encode(questions, show_progress_bar=False)
    k = min(len(questions), TOP_K)
    nn_model = NearestNeighbors(n_neighbors=k, metric="cosine")
    nn_model.fit(embeddings)

def initialize_memory():
    global questions, answers, token_sets
    data = load_faq_data()
    questions[:] = [d["question"] for d in data]
    answers[:] = [d["answer"] for d in data]
    token_sets[:] = [tokens_from_text(q) for q in questions]
    if questions:
        build_index_from_memory()
        print(f"✅ تم تحميل {len(questions)} سؤال وبناء الفهرس.")

initialize_memory()

# ==================== تحليل النص ====================
AR_NUM_WORDS = {
    "واحدة": 1, "واحد": 1, "اثنين": 2, "ثنتين": 2, "ثلاث": 3, "ثلاثة": 3,
    "أربع": 4, "أربعة": 4, "اربعة": 4, "خمسة": 5, "ست": 6, "ستة": 6,
    "سبع": 7, "سبعة": 7, "ثمان": 8, "ثمانية": 8, "تسع": 9, "عشر": 10, "عشرة": 10
}

def extract_hours_from_text(text):
    if not text:
        return None
    text = text.lower()
    # ابحث عن رقم مباشر
    num_match = re.search(r'(\d+)', text)
    if num_match:
        num = int(num_match.group(1))
        if 1 <= num <= 24:
            return num
    # ابحث عن كلمة رقمية بالعربية
    for word, val in AR_NUM_WORDS.items():
        if word in text:
            return val
    return None

# ==================== استدعاءات API ====================
def fetch_resource_groups(service_id):
    try:
        url = SERVICE_ENDPOINTS["resource_groups"].format(serviceId=service_id)
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as e:
        print("fetch_resource_groups error:", e)
        return []

def fetch_fixed_package(stepId, nationalityId, shift=1):
    try:
        url = SERVICE_ENDPOINTS["fixed_package"].format(stepId=stepId, nationalityId=nationalityId, shift=shift)
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        return r.json().get("data", {})
    except Exception as e:
        print("fetch_fixed_package error:", e)
        return {}

def find_service_by_keyword(text):
    mapping = {
        "تنظيف": "1f9b952b-60dc-ee11-b772-000d3a236f24",
        "تنظيف بلس": "9c273825-4fdd-ee11-b772-000d3a236f24",
        "ضيافة": "0ef5bce8-6257-f011-b78d-000d3a236f24",
        "جليسة": "e0f43214-d583-ef11-b77b-000d3a236f24",
        "طباخة": "da502fd9-a36a-ef11-b77a-000d3a236f24"
    }
    for kw, sid in mapping.items():
        if kw in text:
            return kw, sid
    return None, None

# ==================== ديناميكية الأسعار ====================
def get_dynamic_answer_for_price(text):
    text = text.lower()
    if not any(x in text for x in ["سعر", "كم", "تكلفة", "price", "cost", "عرض"]):
        return None

    kw, service_id = find_service_by_keyword(text)
    if not service_id:
        return None

    groups = fetch_resource_groups(service_id)
    if not groups:
        return None

    first_group = groups[0]
    nationalityId = first_group["key"]
    nationalityName = first_group["value"]

    step_id = "2006851d-e10e-4217-b7aa-919d20e08993"
    data = fetch_fixed_package(step_id, nationalityId, shift=1)
    pkgs = data.get("selectedPackages", [])
    if not pkgs:
        return None

    wanted_hours = extract_hours_from_text(text)
    chosen_pkg = None

    # ابحث عن باقة بنفس عدد الساعات أو الأقرب
    if wanted_hours:
        closest_diff = 999
        for pkg in pkgs:
            pkg_hours = int(pkg.get("visitHours") or pkg.get("hoursNumber") or 0)
            diff = abs(pkg_hours - wanted_hours)
            if diff < closest_diff:
                closest_diff = diff
                chosen_pkg = pkg
    else:
        chosen_pkg = pkgs[0]

    name = chosen_pkg.get("displayName", "")
    hours = chosen_pkg.get("visitHours") or chosen_pkg.get("hoursNumber")
    final_price = float(chosen_pkg.get("finalPrice") or 0)
    promo = chosen_pkg.get("promotionOfferList", [])
    promo_text = ""
    if promo:
        promo_text = " — " + "; ".join(p.get("promotionDescription", "") for p in promo)

    return f"لخدمة '{kw}' ({nationalityName}): {name} لمدة {hours} ساعات بسعر {final_price:.2f} ريال{promo_text}"

# ==================== FAQ ====================
def get_best_answer_from_faq(user_input):
    if not questions:
        return None
    user_vec = embedder.encode([user_input])
    dist, idxs = nn_model.kneighbors(user_vec, n_neighbors=min(TOP_K, len(questions)))
    best_idx = idxs[0][0]
    return answers[best_idx]

# ==================== ترجمة ====================
def translate_with_gemini(text, target_lang="Arabic"):
    try:
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        resp = model.generate_content(f"Translate to {target_lang} only:\n{text}")
        return resp.text.strip()
    except Exception:
        return text

# ==================== CHAT ====================

@app.route("/chat", methods=["POST"])
def chat():
    body = request.json or {}
    user_input_raw = body.get("message", "")
    context = body.get("context", {}) or {}

    current_page = context.get("currentPage", "")
    visible_data = context.get("visibleData", {})

    # 🔥 التعامل مع السياق قبل البحث
    if current_page == "HourlyPackagesPage":
        service = visible_data.get("selectedService", "")
        packages = visible_data.get("availablePackages", [])
        offers = visible_data.get("offers", [])

        # لو السؤال فيه كلمة "سعر" أو "تكلفة" والبوت عارف الباقات من الصفحة:
        if any(word in user_input_raw for word in ["سعر", "تكلفة", "price", "cost"]):
            if packages:
                return jsonify({
                    "reply": f"بالنسبة لـ {service}، الباقات المتاحة هي: {', '.join(packages)}. "
                             f"حاليًا يوجد {offers[0] if offers else 'لا يوجد عروض حالياً'}."
                })

    # 🔁 باقي المنطق (اكتشاف اللغة + البحث في FAQ + الترجمة)
    user_input = user_input_raw
    candidate_answer = get_best_answer_from_faq(user_input)

    if not candidate_answer:
        candidate_answer = "لم أجد إجابة مناسبة حالياً، يمكنك إعادة صياغة السؤال."

    return jsonify({"reply": candidate_answer})

if __name__ == "__main__":
    app.run(port=5000, debug=True)
