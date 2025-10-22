def token_overlap_score(q_tokens, c_tokens):
    if not c_tokens:
        return 0.0
    return len(set(q_tokens) & set(c_tokens)) / max(len(c_tokens), 1)
