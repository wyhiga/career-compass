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

def format_company_block(e):
    sources_md = []
    for s in e.get("sources", []):
        sources_md.append(f"[{s}]({s})")
    
    return f"""
---

**{e.get('company_name')}** — {e.get('hq_country')} · {e.get('industry_primary')} · Tier {e.get('asia_tier')} · {e.get('company_size')}

**Why it fits:** {e.get('why_it_fits')}

**Confidence:** {e.get('confidence')} — {e.get('confidence_reason')}

**Role archetypes likely present:** {", ".join(e.get('role_archetypes_likely', []))}

**Flags:** {", ".join(e.get('flags', [])) if e.get('flags') else "None"}

**Suggested next action:** {e.get('suggested_next_action')}

**Sources:** {", ".join(sources_md)}

---
"""

def compose_email(evaluations_file):
    try:
        with open(evaluations_file, "r") as f:
            evaluations = json.load(f)
        
        today = date.today().isoformat()
        
        # 1. Generate Lede with Gemini
        print("[*] Generating Lede with Gemini...")
        in_scope = [e for e in evaluations if e.get("in_scope") and e.get("asia_tier") in ["A", "B"]]
        watch_list = [e for e in evaluations if e.get("in_scope") and e.get("asia_tier") == "C"]
        
        lede_prompt_template = Path("prompts/email_lede.md").read_text()
        lede_input = lede_prompt_template.replace("[DATE]", today)
        lede_input = lede_input.replace("[TOTAL]", str(len(evaluations)))
        lede_input = lede_input.replace("[IN_SCOPE_NAMES]", ", ".join([e['company_name'] for e in in_scope]))
        lede_input = lede_input.replace("[WATCH_LIST_NAMES]", ", ".join([e['company_name'] for e in watch_list]))
        
        lede_response = client.models.generate_content(model='gemini-2.5-flash', contents=lede_input)
        lede_text = lede_response.text
        
        # 2. Format Company Blocks with Python
        print("[*] Formatting company blocks with Python...")
        in_scope_html = "\n".join([format_company_block(e) for e in in_scope])
        watch_list_html = "\n".join([format_company_block(e) for e in watch_list])
        
        # 3. Generate Quality Notes with Gemini
        print("[*] Generating Quality Notes with Gemini...")
        notes_prompt_template = Path("prompts/email_notes.md").read_text()
        all_gaps = []
        for e in evaluations:
            if e.get("verification_gaps"):
                all_gaps.append(f"{e['company_name']}: {', '.join(e['verification_gaps'])}")
        
        out_of_scope_count = len([e for e in evaluations if not e.get("in_scope")])
        
        notes_input = notes_prompt_template.replace("[TOTAL]", str(len(evaluations)))
        notes_input = notes_input.replace("[EXCLUDED_COUNT]", str(out_of_scope_count))
        notes_input = notes_input.replace("[GAPS_TEXT]", "\n".join(all_gaps[:10])) # Cap to avoid long prompts
        
        notes_response = client.models.generate_content(model='gemini-2.5-flash', contents=notes_input)
        notes_text = notes_response.text
        
        # 4. Assemble Final Email
        final_email = f"""# Career Compass — Week of {today}

{lede_text}

## In-Scope Opportunities (Tier A & B)
{in_scope_html if in_scope else "No new Tier A or B companies found this week."}

## Watch List (Tier C)
{watch_list_html if watch_list else "No Tier C companies this week."}

{notes_text}

---
Full evaluation data for this run is saved in `data/runs/evaluations_{today}.json`
"""
        
        output_path = Path(f"outputs/email_{today}.md")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(final_email)
        
        # Update Dashboard data
        dashboard_data_path = Path("dashboard/data.js")
        input_data = {"run_metadata": {"run_date": today, "count": len(evaluations)}, "evaluations": evaluations}
        with open(dashboard_data_path, "w") as dj:
            dj.write(f"const dashboardData = {json.dumps(input_data, indent=2)};")
            
        print(f"[+] Email composed successfully: {output_path}")
        return output_path

    except Exception as e:
        print(f"An error occurred in Composition: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        compose_email(sys.argv[1])
    else:
        print("Usage: python3 composition.py path/to/evaluations.json")
