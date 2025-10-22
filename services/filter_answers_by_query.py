from .tokens_from_text import tokens_from_text
from .normalize_ar import normalize_ar


def filter_answers_by_query(user_text, data, min_token_len=4):
    tokens = [t for t in tokens_from_text(user_text) if len(t) >= min_token_len]
    if not tokens:
        return None

    matches = []
    required_matches = max(1, len(tokens))

    for topic in data:
        for qa in topic.get("questions", []):
            for ans in qa.get("answers", []):
                norm_ans = normalize_ar(ans)
                matched_tokens = 0

                for tok in tokens:
                    if tok in norm_ans:
                        matched_tokens += 1
                        if matched_tokens >= required_matches:
                            matches.append(ans)
                            break

            if matched_tokens < required_matches:
                norm_q = normalize_ar(qa.get("question", ""))
                for tok in tokens:
                    if tok in norm_q:
                        matched_tokens += 1
                        if matched_tokens >= required_matches:
                            matches.extend(qa.get("answers", []))
                            break

    if matches:
        unique_answers = list(dict.fromkeys(matches))[:2]
        return "\n".join(unique_answers)
    return None
