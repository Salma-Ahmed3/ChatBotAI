from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import json, os

app = Flask(__name__)
FAQ_PATH = os.path.join(os.path.dirname(__file__), "faq.json")
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# ----------------------------
# تحميل البيانات
# ----------------------------
def load_faq_data():
    if not os.path.exists(FAQ_PATH):
        return []
    with open(FAQ_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

faq_data = load_faq_data()

# ----------------------------
# دالة البحث الذكي
# ----------------------------
def smart_search(user_question):
    user_vec = embedder.encode([user_question])
    best_score = 0
    best_answers = []

    for topic in faq_data:
        for q in topic.get("questions", []):
            q_vec = embedder.encode([q["question"]])
            score = cosine_similarity(user_vec, q_vec)[0][0]
            if score > best_score:
                best_score = score
                best_answers = q["answers"]

    if not best_answers:
        return ["عذرًا، لا توجد إجابة حالياً."]

    # 🔍 استخراج الكلمات المهمة من السؤال
    keywords = [w.strip("؟,.،") for w in user_question.split() if len(w) > 5]

    # ✅ فلترة دقيقة: نختار الإجابات التي تحتوي على أي من الكلمات
    filtered_answers = []
    for ans in best_answers:
        for k in keywords:
            if k in ans or k[:-1] in ans or k[:-2] in ans:  # يراعي التصريف مثل "الساعات" و"الساعة"
                filtered_answers.append(ans)
                break

    # لو في فلترة ناجحة → نرجعها فقط
    if filtered_answers:
        return filtered_answers

    # لو السؤال عام → نرجع الكل
    return best_answers

# ----------------------------
# واجهة الـ API
# ----------------------------
@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "").strip()
    if not user_input:
        return jsonify({"reply": "يرجى كتابة رسالة."})

    matched_answers = smart_search(user_input)
    combined = "\n".join([f"• {a}" for a in matched_answers])
    return jsonify({"reply": combined})

# ----------------------------
# تشغيل السيرفر
# ----------------------------
if __name__ == "__main__":
    app.run(port=5000, debug=True)
