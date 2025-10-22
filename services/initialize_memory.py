from .load_faq_data import load_faq_data
from .state import QUESTIONS, ANSWERS, TOKEN_SETS
from .tokens_from_text import tokens_from_text
from .build_index_from_memory import build_index_from_memory


def initialize_memory():
    global QUESTIONS, ANSWERS, TOKEN_SETS
    data = load_faq_data()

    QUESTIONS.clear()
    ANSWERS.clear()
    TOKEN_SETS.clear()

    for topic in data:
        for qa in topic.get("questions", []):
            question = qa.get("question", "")
            answer_list = qa.get("answers", [])

            if question and answer_list:
                QUESTIONS.append(question)
                ANSWERS.append("\n".join(answer_list))
                TOKEN_SETS.append(tokens_from_text(question))

    if QUESTIONS:
        build_index_from_memory()
        print(f"✅ تم تحميل {len(QUESTIONS)} سؤال وبناء الفهرس بنجاح.")
    else:
        print("⚠️ لا توجد أسئلة محفوظة بعد.")
