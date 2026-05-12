from composition import compose_email
from pathlib import Path

eval_file = Path("data/runs/evaluations_2026-05-12.json")
if eval_file.exists():
    email = compose_email(eval_file)
    print("Success! Generated email:", email)
else:
    print("Eval file does not exist")
