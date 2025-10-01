
from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import NearestNeighbors
import google.generativeai as genai
import json
import os

app = Flask(__name__)
genai.configure(api_key="AIzaSyBEeidGnK_uyf9ikJWW9elsAgDdz8t09oA")  # ← ضيف API KEY بتاعك

# تحديد مسار faq.json (مطلق عشان نتجنب مشاكل اختلاف المجلدات)
FAQ_PATH = os.path.join(os.path.dirname(__file__), "faq.json")

# نموذج تحويل النص إلى Embeddings
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# تحميل البيانات
with open(FAQ_PATH, "r", encoding="utf-8") as f:
    faq_data = json.load(f)

questions = [item["question"] for item in faq_data]
answers = [item["answer"] for item in faq_data]

# تجهيز Embeddings
embeddings = embedder.encode(questions)
nn_model = NearestNeighbors(n_neighbors=1, metric="cosine")
nn_model.fit(embeddings)

# نخزن آخر سؤال مضاف عشان نقدر نعدّل عليه لاحقًا
last_added_question = None


# --- دوال إدارة JSON ---

def save_new_faq(question, answer="سيتم التعديل على الإجابة لاحقاً"):
    """إضافة سؤال جديد مع إجابة افتراضية للملف (بدون تكرار)"""
    with open(FAQ_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # تحقق إذا السؤال موجود بالفعل
    for item in data:
        if item["question"].strip() == question.strip():
            return  # موجود بالفعل → لا تضيفه تاني

    # لو مش موجود → أضفه
    data.append({"question": question, "answer": answer})

    with open(FAQ_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # تحديث الذاكرة الداخلية
    questions.append(question)
    answers.append(answer)
    query_vecs = embedder.encode(questions)
    nn_model.fit(query_vecs)


def update_answer(question, new_answer):
    """تعديل إجابة سؤال موجود"""
    with open(FAQ_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        if item["question"].strip() == question.strip():
            item["answer"] = new_answer
            break

    with open(FAQ_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # تحديث الذاكرة الداخلية
    idx = questions.index(question)
    answers[idx] = new_answer
    query_vecs = embedder.encode(questions)
    nn_model.fit(query_vecs)


# --- منطق الرد ---

def get_best_answer(user_input):
    global last_added_question

    # لو المستخدم بيعدل الإجابة
    if user_input.startswith("الرد الصحيح هو"):
        new_answer = user_input.replace("الرد الصحيح هو", "").strip()
        if last_added_question:
            update_answer(last_added_question, new_answer)
            return f"تم تعديل الإجابة لتكون: {new_answer}"
        else:
            return "مافيش سؤال سابق لتعديله."

    # البحث بالـ embeddings (الأدق)
    if questions:
        query_vec = embedder.encode([user_input])
        dist, idx = nn_model.kneighbors(query_vec, n_neighbors=1)
        similarity = 1 - dist[0][0]  # cosine similarity

        if similarity >= 0.75:  # العتبة الأعلى تفرق بين العقود / الطلبات
            last_added_question = questions[idx[0][0]]
            return answers[idx[0][0]]

    # لو مفيش تطابق قوي → سجل السؤال كجديد
    last_added_question = user_input
    save_new_faq(user_input)
    return "تم إضافة سؤالك إلى قاعدة البيانات، يمكنك تعديل الإجابة بقول: الرد الصحيح هو ..."


@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "")

    # البحث أو الإضافة
    custom_answer = get_best_answer(user_input)

    # صياغة الرد النهائي باستخدام Gemini
    model = genai.GenerativeModel("models/gemini-2.5-pro")
    prompt = (
        f"السؤال: {user_input}\n"
        f"الإجابة من قاعدة البيانات: {custom_answer}\n"
        "من فضلك أجب رد واحد فقط وواضح، لا تعطي خيارات متعددة أو أساليب مختلفة، واجعل الرد ودود وسهل الفهم."
        "إذا كان السؤال باللغة غير العربيه قم بترجمته ورد بنفس اللغة"
        " اذا اخبرك احدا باي رسالة ترحيب قم بالرد عليه برسالة الترحيب المناسبه مع كيف يمكنني مساعدتك"
        "اذا طلب منك احدا ان تقدم نفسك قم بالرد عليه : انا مساعد افتراضي تم تطويره تابع لشركة معين | Mueen لمساعدتك في الاستفسارات المتعلقة بالتطبيقات والخدمات التي نقدمها. كيف يمكنني مساعدتك اليوم؟"
        "اذا طلب منك احدا ان تقدم له المساعدة قم بالرد عليه : بالتأكيد! أنا هنا لمساعدتك. من فضلك أخبرني بما تحتاجه."
        "اذا طلب منك احدا ان تقدم له الشكر قم بالرد عليه : على الرحب والسعة! إذا كنت بحاجة إلى أي مساعدة أخرى، فلا تتردد في السؤال."
        "اذا سألك شخص سؤال وعندما قمت بالرد واخبرك ان هذا رد خاطئ و اخبرك بالرد الصحيح قم بتخزين الرد الصحيح في قاعدة البيانات الخاصه بك و قم بالرد عليه بالرد الصحيح الذي اخبرك به"
    )
    response = model.generate_content(prompt)
    final_reply = response.text.strip().split("\n")[0]

    return jsonify({"reply": final_reply})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
