from google import genai
from google.genai import types
import os
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

# Configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("Error: GOOGLE_API_KEY not found in .env file.")
    exit(1)

client = genai.Client(api_key=GOOGLE_API_KEY)


# Failure mode constants. Knowing which mode killed a company is the difference
# between "transient hiccup, will pass next run" and "the prompt is producing
# bad JSON, fix the prompt."
FAILURE_API_ERROR = "api_error"          # network, rate limit, 5xx after retries
FAILURE_PARSE_ERROR = "parse_error"      # response wasn't valid JSON
FAILURE_SCHEMA_INVALID = "schema_invalid"  # JSON parsed but missing required fields
FAILURE_TIMEOUT = "timeout"              # per-company timeout in main loop
FAILURE_UNKNOWN = "unknown"

# Fields every evaluation MUST have to be usable downstream by composition.py.
# Optional fields (out_of_scope_reason, flags, verification_gaps) are not in
# this list because they're conditionally present or allowed to be empty.
REQUIRED_EVALUATION_FIELDS = [
    "company_name",
    "hq_country",
    "in_scope",
    "asia_tier",
    "industry_primary",
    "company_size",
    "why_it_fits",
    "confidence",
    "confidence_reason",
    "role_archetypes_likely",
    "suggested_next_action",
    "sources",
]


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=5, max=20))
def call_evaluation_api(prompt):
    return client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}]
        )
    )


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


def validate_evaluation_schema(evaluation):
    """
    Returns (is_valid, list_of_missing_fields).
    Missing or empty-string required fields both count as missing.
    """
    if not isinstance(evaluation, dict):
        return False, ["<not a dict>"]

    missing = []
    for field in REQUIRED_EVALUATION_FIELDS:
        if field not in evaluation:
            missing.append(field)
            continue
        value = evaluation[field]
        # Allow `in_scope: false`, but not empty strings or None on text fields
        if value is None:
            missing.append(field)
        elif isinstance(value, str) and not value.strip():
            missing.append(field)
        elif isinstance(value, list) and len(value) == 0 and field in ("role_archetypes_likely", "sources"):
            # Empty list is only a problem for in-scope companies
            if evaluation.get("in_scope") is True:
                missing.append(field)

    return len(missing) == 0, missing


def make_failure_record(candidate, reason, detail, raw_response=None):
    """Build a structured failure record for the failures file."""
    record = {
        "company_name": candidate.get("company_name", "<unknown>"),
        "hq_country_guess": candidate.get("hq_country_guess", ""),
        "failure_reason": reason,
        "failure_detail": str(detail)[:500],  # truncate long stack traces
    }
    if raw_response is not None:
        # Cap raw response to keep failures file small
        record["raw_response_excerpt"] = str(raw_response)[:2000]
    return record


def evaluate_company(candidate):
    """
    Evaluate one candidate. Returns one of:
      ("success", evaluation_dict)
      ("failure", failure_record_dict)
    Never returns None — that was the old bug.
    """
    evaluation_prompt_path = Path("prompts/evaluation.md")
    cv_path = Path("reference/wendy_cv.md")
    rubric_path = Path("reference/rubric.md")

    evaluation_template = evaluation_prompt_path.read_text()
    cv_text = cv_path.read_text()
    rubric_text = rubric_path.read_text()

    final_prompt = evaluation_template.replace("[CV_TEXT]", cv_text)
    final_prompt = final_prompt.replace("[RUBRIC_TEXT]", rubric_text)
    final_prompt = final_prompt.replace("[COMPANY_NAME]", candidate["company_name"])
    final_prompt = final_prompt.replace("[HQ_COUNTRY_GUESS]", candidate["hq_country_guess"])
    final_prompt = final_prompt.replace("[WHY_CANDIDATE]", candidate["why_candidate"])

    # Stage 1: API call
    try:
        response = call_evaluation_api(final_prompt)
    except Exception as e:
        print(f"[-] API error for {candidate['company_name']}: {e}")
        return ("failure", make_failure_record(candidate, FAILURE_API_ERROR, e))

    raw_text = getattr(response, "text", "") or ""

    # Stage 2: JSON parse
    try:
        evaluation = extract_json(raw_text)
    except Exception as e:
        print(f"[-] Parse error for {candidate['company_name']}: {e}")
        return ("failure", make_failure_record(
            candidate, FAILURE_PARSE_ERROR, e, raw_response=raw_text
        ))

    # Stage 3: Schema validation
    is_valid, missing = validate_evaluation_schema(evaluation)
    if not is_valid:
        print(f"[-] Schema invalid for {candidate['company_name']}: missing {missing}")
        return ("failure", make_failure_record(
            candidate,
            FAILURE_SCHEMA_INVALID,
            f"Missing or empty required fields: {missing}",
            raw_response=raw_text,
        ))

    return ("success", evaluation)


def run_all_evaluations(candidates_file):
    with open(candidates_file, "r") as f:
        candidates = json.load(f)

    total = len(candidates)
    print(f"\n[+] Starting parallel evaluation of {total} companies (Max 5 at a time)...")

    output_dir = Path("data/runs")
    output_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    results_file = output_dir / f"evaluations_{today}.json"
    failures_file = output_dir / f"failures_{today}.json"

    if not candidates:
        print("No new candidates to evaluate.")
        if results_file.exists():
            print(f"Found existing evaluations for today: {results_file}")
            return results_file
        else:
            print("No existing evaluations found for today.")
            return None

    results = []
    failures = []

    # Load existing results for today if they exist (resume-after-crash behavior)
    if results_file.exists():
        try:
            with open(results_file, "r") as f:
                results = json.load(f)
            print(f"Loaded {len(results)} existing results for today.")
        except Exception:
            results = []
    if failures_file.exists():
        try:
            with open(failures_file, "r") as f:
                failures = json.load(f)
            print(f"Loaded {len(failures)} existing failures for today.")
        except Exception:
            failures = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_company = {
            executor.submit(evaluate_company, c): c for c in candidates
        }

        completed = 0
        for future in as_completed(future_to_company):
            candidate = future_to_company[future]
            company_name = candidate["company_name"]
            try:
                outcome, payload = future.result(timeout=300)
                if outcome == "success":
                    results.append(payload)
                else:
                    failures.append(payload)
            except Exception as e:
                # Timeout or executor-level error — catch and record
                print(f"[-] Timeout/executor error for {company_name}: {e}")
                failures.append(make_failure_record(
                    candidate, FAILURE_TIMEOUT, e
                ))

            completed += 1
            print(f"[{completed}/{total}] Finished evaluation for {company_name}")

    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)

    # Write failures file. Always write it, even if empty — composition.py
    # uses its presence-with-content as the signal to render the failures
    # section. Empty array = no section.
    with open(failures_file, "w") as f:
        json.dump(failures, f, indent=2)

    print(f"\nEvaluation complete.")
    print(f"  Successes: {len(results)}")
    print(f"  Failures:  {len(failures)}")
    print(f"  Saved to:  {results_file}")
    if failures:
        print(f"  Failures:  {failures_file}")
        # Print a one-line summary by reason for the CI log
        from collections import Counter
        reason_counts = Counter(f["failure_reason"] for f in failures)
        for reason, n in reason_counts.most_common():
            print(f"    - {reason}: {n}")

    return results_file


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_all_evaluations(sys.argv[1])
    else:
        print("Usage: python3 evaluation.py path/to/candidates.json")
