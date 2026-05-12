from google import genai
from google.genai import types
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

try:
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents="Hello, please return a JSON object with 'status'='ok'",
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}]
        )
    )
    print("Success:", response.text)
except Exception as e:
    print("Error:", repr(e))
