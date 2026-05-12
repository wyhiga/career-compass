from google import genai
from google.genai import types
import os
import json
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

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=10, max=60))
def generate_candidates(prompt):
    return client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}]
        )
    )

import re

def extract_json(text):
    text = text.strip()
    # Try to find JSON block in markdown
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    # If no markdown, just try to parse the text directly (might be pure JSON)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback to finding the first [ and last ]
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1:
            return json.loads(text[start:end+1])
        raise

def get_already_surfaced_companies():
    """Scans data/runs for previous candidates and evaluations to avoid repetition."""
    surfaced = set()
    runs_dir = Path("data/runs")
    if not runs_dir.exists():
        return "None (Initial Run)"
    
    for file in runs_dir.glob("*.json"):
        try:
            with open(file, "r") as f:
                data = json.load(f)
                # If it's a list of candidates or evaluations
                if isinstance(data, list):
                    for item in data:
                        name = item.get("company_name")
                        if name:
                            surfaced.add(name)
                # If it's the structured dashboard data
                elif isinstance(data, dict) and "evaluations" in data:
                    for item in data["evaluations"]:
                        name = item.get("company_name")
                        if name:
                            surfaced.add(name)
        except Exception:
            continue
            
    if not surfaced:
        return "None (Initial Run)"
    
    return ", ".join(sorted(list(surfaced)))

def run_discovery():
    discovery_prompt_path = Path("prompts/discovery.md")
    exclusions_path = Path("reference/excluded_companies.md")
    
    # NEW: Fetch already surfaced companies from history
    already_surfaced = get_already_surfaced_companies()
    
    discovery_template = discovery_prompt_path.read_text()
    exclusions_text = exclusions_path.read_text()
    
    # Prepare the final prompt
    final_prompt = discovery_template.replace("[ALREADY_SURFACED]", already_surfaced)
    final_prompt = final_prompt.replace("[EXCLUDED_COMPANIES]", exclusions_text)
    
    print(f"Starting Discovery stage... (Excluding {already_surfaced.count(',') + 1 if 'None' not in already_surfaced else 0} known companies)")
    
    try:
        # We enforce JSON output in the prompt, but we can also set the response_mime_type
        response = generate_candidates(final_prompt)
        
        candidates = extract_json(response.text)
        
        # Save candidates for Stage 2
        output_dir = Path("data/runs")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        from datetime import date
        today = date.today().isoformat()
        run_file = output_dir / f"candidates_{today}.json"
        
        with open(run_file, "w") as f:
            json.dump(candidates, f, indent=2)
            
        print(f"Discovery complete. Found {len(candidates)} candidates.")
        print(f"Saved to: {run_file}")
        return candidates

    except Exception as e:
        print(f"An error occurred in Discovery: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    run_discovery()
