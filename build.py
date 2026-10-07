"""Повна збірка проєкту однією командою.

    python build.py            # графіки, прогноз, документи, презентація (+ PDF через PowerPoint)
    python build.py --fetch    # спершу завантажити свіжі дані (API НБУ, ЄЦБ, Eurostat)
    python build.py --no-pdf   # без експорту PDF

Кроки: update_data -> overview data/charts -> run_forecast -> run_irfs -> make_docs -> deck -> PDF -> tests
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def step(title, cmd, env=None):
    print(f"\n=== {title}")
    r = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})})
    if r.returncode != 0:
        sys.exit(f"Помилка на кроці «{title}»")


def main():
    fetch = "--fetch" in sys.argv
    if fetch:
        step("Оновлення даних моделі", [PY, "update_data.py"])
    step("Дані та графіки огляду", [PY, "make_overview_charts.py"] + (["--fetch"] if fetch else []))
    step("Фільтр, прогноз, сценарії", [PY, "run_forecast.py"])
    step("Функції відгуку", [PY, "run_irfs.py"])
    step("Документація", [PY, "make_docs.py"])
    step("Зміст презентації", [PY, "deck/content.py"])
    step("Презентація (pptxgenjs)", ["node", "deck/build_deck.js"],
         env={"NODE_PATH": str(ROOT / "deck" / "node_modules")})
    if "--no-pdf" not in sys.argv and os.name == "nt":
        step("PDF (PowerPoint)", ["powershell", "-ExecutionPolicy", "Bypass", "-File", "deck/export.ps1"])
    step("Тести", [PY, "-m", "pytest", "-q"])
    print("\nГотово: presentation/NBU_University_Challenge_2026.pptx (+ .pdf), docs/, results/")


if __name__ == "__main__":
    main()
