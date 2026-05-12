from google import genai
from google.genai import types
import os
import json
import sys
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
def call_evaluation_api(prompt):
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
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback to finding the first { and last }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return json.loads(text[start:end+1])
        raise

def evaluate_company(candidate):
    evaluation_prompt_path = Path("prompts/evaluation.md")
    cv_path = Path("reference/wendy_cv.md")
    rubric_path = Path("reference/rubric.md")
    
    evaluation_template = evaluation_prompt_path.read_text()
    cv_text = cv_path.read_text()
    rubric_text = rubric_path.read_text()
    
    # Prepare the final prompt
    final_prompt = evaluation_template.replace("[CV_TEXT]", cv_text)
    final_prompt = final_prompt.replace("[RUBRIC_TEXT]", rubric_text)
    final_prompt = final_prompt.replace("[COMPANY_NAME]", candidate["company_name"])
    final_prompt = final_prompt.replace("[HQ_COUNTRY_GUESS]", candidate["hq_country_guess"])
    final_prompt = final_prompt.replace("[WHY_CANDIDATE]", candidate["why_candidate"])
    
    
    try:
        response = call_evaluation_api(final_prompt)
        
        evaluation = extract_json(response.text)
        return evaluation

    except Exception as e:
        print(f"An error occurred in Evaluation for {candidate['company_name']}: {e}")
        return None

def run_all_evaluations(candidates_file):
    with open(candidates_file, "r") as f:
        candidates = json.load(f)
        
    results = []
    
    # Process one by one to avoid quota issues
    for i, candidate in enumerate(candidates):
        print(f"\n[{i+1}/{len(candidates)}] Evaluating {candidate['company_name']}...")
        result = evaluate_company(candidate)
        if result:
            results.append(result)
            
    # Save results
    output_dir = Path("data/runs")
    from datetime import date
    today = date.today().isoformat()
    results_file = output_dir / f"evaluations_{today}.json"
    
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
        
    print(f"Evaluation complete. Processed {len(results)} companies.")
    print(f"Saved to: {results_file}")
    return results_file

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_all_evaluations(sys.argv[1])
    else:
        print("Usage: python3 evaluation.py path/to/candidates.json")
