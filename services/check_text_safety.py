import google.generativeai as genai

def check_text_safety(text):
    """التحقق من سلامة النص باستخدام Gemini"""
    try:
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        prompt = f"""
        Analyze if this text contains any offensive content like:
        - Insults
        - Hate speech
        - Profanity
        - Threats
        - Inappropriate language
        
        Reply ONLY with "SAFE" or "UNSAFE". Nothing else.
        
        Text to analyze:
        {text}
        """

        resp = model.generate_content(prompt)
        result = resp.text.strip().upper()
        return result == "SAFE"
    except Exception as e:
        print("⚠️ خطأ في فحص سلامة النص:", e)
        return True
