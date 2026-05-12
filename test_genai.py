import os
from google import genai
from google.genai import types

def test():
    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents='Hello',
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}]
        )
    )
    print(response.text)

test()
