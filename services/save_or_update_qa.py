import json
from .load_faq_data import load_faq_data
from .tokens_from_text import tokens_from_text
from .token_overlap_score import token_overlap_score
from .initialize_memory import initialize_memory
from .extract_topic import extract_topic
from .state import FAQ_PATH


def save_or_update_qa(question, answer):
    data = load_faq_data()
    q_tokens = tokens_from_text(question)
    found_idx = None
    found_topic = None

    for topic in data:
        for qa in topic.get("questions", []):
            if token_overlap_score(q_tokens, tokens_from_text(qa["question"])) >= 0.6:
                found_topic = topic
                found_idx = data.index(topic)
                break
        if found_topic:
            break

    answer_list = answer.split("\n") if isinstance(answer, str) else answer

    if found_topic:
        for qa in found_topic["questions"]:
            if token_overlap_score(q_tokens, tokens_from_text(qa["question"])) >= 0.6:
                qa["answers"] = answer_list
                break
    else:
        new_topic = {
            "topic": extract_topic(question),
            "questions": [{
                "question": question,
                "answers": answer_list
            }]
        }
        data.append(new_topic)

    with open(FAQ_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    initialize_memory()
