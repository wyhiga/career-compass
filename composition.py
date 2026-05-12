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
    
    in_scope = [e for e in evaluations if e.get("in_scope") and e.get("asia_tier") in ["A", "B"]]
    watch_list = [e for e in evaluations if e.get("in_scope") and e.get("asia_tier") == "C"]
    out_of_scope = [e for e in evaluations if not e.get("in_scope")]
    
    input_data = {
        "run_metadata": {
            "run_id": run_id,
            "run_date": today,
            "companies_investigated": len(evaluations),
            "companies_excluded": len(out_of_scope)
        },
        "evaluations": evaluations
    }
    
    final_prompt = composition_template
    # We pass the input data as a block of text at the end or embedded
    final_prompt += f"\n\nINPUT DATA:\n{json.dumps(input_data, indent=2)}"
    
    print("Composing final email...")
    
    try:
        response = call_composition_api(final_prompt)
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
