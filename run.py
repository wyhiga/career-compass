import os
from datetime import date
from dotenv import load_dotenv
from pathlib import Path

# Importar las funciones de cada etapa
from discovery import run_discovery
from evaluation import run_all_evaluations
from composition import compose_email

load_dotenv()

def main():
    print("[*] Script started. Initializing...")
    today = date.today().isoformat()
    print(f"\n{'='*40}")
    print(f" Career Compass Run: {today}")
    print(f"{'='*40}\n")
    
    # 1. Etapa de Descubrimiento (Discovery)
    # Busca empresas candidatas basadas en la rúbrica.
    candidates = run_discovery()
    if not candidates:
        print("[-] Error en Discovery o no se encontraron candidatos. Abortando.")
        return
    
    candidates_file = Path(f"data/runs/candidates_{today}.json")
    
    # 2. Etapa de Evaluación (Evaluation)
    # Investiga cada empresa una por una usando búsqueda web.
    print("\n[+] Iniciando fase de evaluación detallada...")
    eval_results_file = run_all_evaluations(candidates_file)
    if not eval_results_file:
        print("[-] Error en Evaluation. Abortando.")
        return
    
    # 3. Etapa de Composición (Composition)
    # Genera el email final en Markdown.
    print("\n[+] Componiendo el briefing final...")
    email_file = compose_email(eval_results_file)
    
    if email_file:
        print(f"\n{'='*40}")
        print(f" ¡Ejecución completada con éxito!")
        print(f" Reporte final: {email_file}")
        print(f"{'='*40}\n")

if __name__ == "__main__":
    main()
