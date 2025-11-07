import os
import google.generativeai as genai

API_KEY = os.environ.get("AIzaSyBg1n3SthMHuiSzMyV_SP59PYZof54_aUQ")
if API_KEY:
    genai.configure(api_key=API_KEY)
