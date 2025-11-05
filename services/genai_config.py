import os
import google.generativeai as genai

API_KEY = os.environ.get("AIzaSyDTlNGcG3F0gPqUrJ4m93OZDoHvRdRI52w")
if API_KEY:
    genai.configure(api_key=API_KEY)
