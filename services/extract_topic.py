def extract_topic(question):
    topic = question.replace("ما هي", "").replace("ما هو", "").replace("؟", "").strip()
    words = topic.split()[:3]
    return " ".join(words)
