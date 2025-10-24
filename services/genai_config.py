import os
import google.generativeai as genai

API_KEY = os.environ.get("API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)
