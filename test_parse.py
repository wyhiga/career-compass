import json
from discovery import generate_candidates, run_discovery
from pathlib import Path

discovery_prompt_path = Path("prompts/discovery.md")
exclusions_path = Path("reference/excluded_companies.md")

discovery_template = discovery_prompt_path.read_text()
exclusions_text = exclusions_path.read_text()

final_prompt = discovery_template.replace("[ALREADY_SURFACED]", "None").replace("[EXCLUDED_COMPANIES]", exclusions_text)

print("Prompting Gemini...")
response = generate_candidates(final_prompt)
print("RAW RESPONSE START:")
print(response.text)
print("RAW RESPONSE END")
