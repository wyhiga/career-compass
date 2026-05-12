import json
from datetime import date
from pathlib import Path

evaluations_file = "data/runs/evaluations_2026-05-12.json"
with open(evaluations_file, "r") as f:
    evaluations = json.load(f)

today = date.today().isoformat()
run_id = f"{today}-run"

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

dashboard_data_path = Path("dashboard/data.js")
with open(dashboard_data_path, "w") as dj:
    dj.write(f"const dashboardData = {json.dumps(input_data, indent=2)};")

print("Dashboard data updated manually!")
