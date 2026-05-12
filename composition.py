from google import genai
import os
import json
import sys
from datetime import date
from dotenv import load_dotenv
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

# Configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("Error: GOOGLE_API_KEY not found in .env file.")
    exit(1)

client = genai.Client(api_key=GOOGLE_API_KEY)

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=5, max=20))
def call_composition_api(prompt):
    print(f"[*] Calling Gemini for email composition (Input size: {len(prompt)} chars)...")
    return client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )

def compose_email(evaluations_file):
    composition_prompt_path = Path("prompts/email_composition.md")
    composition_template = composition_prompt_path.read_text()
    
    with open(evaluations_file, "r") as f:
        evaluations = json.load(f)
    
    # Prepare metadata for the prompt
    today = date.today().isoformat()
    run_id = f"{today}-run"
    
    # Strip unnecessary noise to keep the prompt focused and within safe limits
    filtered_evals = []
    out_of_scope_count = 0
    for e in evaluations:
        if not e.get("in_scope"):
            out_of_scope_count += 1
        filtered_e = {k: v for k, v in e.items() if k not in ['search_queries_used', 'verification_gaps']}
        filtered_evals.append(filtered_e)

    input_data = {
        "run_metadata": {
            "run_id": run_id,
            "run_date": today,
            "companies_investigated": len(evaluations),
            "companies_excluded": out_of_scope_count
        },
        "evaluations": filtered_evals
    }
    
    final_prompt = composition_template
    final_prompt += f"\n\nINPUT DATA:\n{json.dumps(input_data, indent=2)}"
    
    print(f"Composing final email (Filtered input: {len(final_prompt)} chars)...")
    
    try:
        # Use more relaxed safety settings to prevent hangs on company names/industries
        from google.genai import types
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=final_prompt,
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category="HATE_SPEECH", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARASSMENT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                ]
            )
        )
        print("[+] Received response from Gemini.")
        email_content = response.text
        
        output_path = Path(f"outputs/email_{today}.md")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(email_content)
        
        print(f"Email composed and saved to: {output_path}")
        
        # New: Update Dashboard data
        dashboard_data_path = Path("dashboard/data.js")
        with open(dashboard_data_path, "w") as dj:
            dj.write(f"const dashboardData = {json.dumps(input_data, indent=2)};")
        print(f"Dashboard data updated at: {dashboard_data_path}")

        return output_path

    except Exception as e:
        print(f"An error occurred in Composition: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        compose_email(sys.argv[1])
    else:
        print("Usage: python3 composition.py path/to/evaluations.json")
