import os
import google.generativeai as genai

API_KEY = os.environ.get("AIzaSyBiVujRK7sBtyHN6ttxewS_2lMzvBEIk1A") or os.environ.get("GOOGLE_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)
