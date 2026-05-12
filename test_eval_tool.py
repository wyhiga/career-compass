import json
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

load_dotenv()
client = genai.Client()

try:
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents="Who is the CEO of Google?",
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}]
        )
    )
    print("Success:", response.text)
except Exception as e:
    print("Error:", e)
