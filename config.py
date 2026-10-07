"""Налаштування прогону моделі. Відповідає блокам у a03_run_filter.m та a04_run_forecast.m.

Змінюйте тут дати, коригування (tunes) і сценарії; код у qpm/ чіпати не треба.
"""

DATA_DIR = "data"
MODEL_FILE = "model/model.model"
PARAMS_FILE = "model/params.yaml"
RESULTS_DIR = "results"

# Діапазони (a03_run_filter.m)
FIRST_HIST = "2016Q1"
LAST_HIST = "2026Q3"      # останній квартал з фактичними даними (ставка, курс; ІСЦ і ВВП за неповні квартали оцінює фільтр)
LAST_FORE = "2028Q4"

# Структурні зломи воєнного часу: std шоку рівня потенційного ВВП лише у 2022Q1-Q2
STD_OVERRIDES = {
    "res_l_gdp_tnd": {"default": 0.0, "periods": {("2022Q1", "2022Q2"): 0.75}},
}

# Коригування розриву ВВП (tunes), % від потенціалу
GDP_GAP_TUNES = {"2015Q1": 0, "2022Q2": -18}

# Зміни параметрів для всього прогону (наприклад {"beta": 0.8}); порожньо = params.yaml
PARAM_OVERRIDES = {}


# ---------------------------------------------------------------------------- сценарії
# Кожен сценарій — функція (plan, f) -> plan, де f = перший прогнозний квартал.
# plan.exogenize(змінна, квартали, значення) + plan.endogenize(шок, ті самі квартали)
# plan.shock(шок, квартали, значення) — ручний шок (судження), без фіксації змінної.

def q(f, k):
    """Квартал f + k."""
    return f + k


def scenario_baseline(plan, f):
    return plan


def scenario_depreciation(plan, f):
    """Альтернатива 1 шаблону НБУ: цільова девальвація 9% річних протягом 4 кварталів."""
    rng = [q(f, i) for i in range(4)]
    plan.exogenize("dl_er_tar", rng, 9)
    plan.endogenize("res_dl_er_tar", rng)
    return plan


def scenario_appreciation(plan, f):
    """Альтернатива 2 шаблону НБУ: ревальвація 1% річних протягом 4 кварталів."""
    rng = [q(f, i) for i in range(4)]
    plan.exogenize("dl_er_tar", rng, -1)
    plan.endogenize("res_dl_er_tar", rng)
    return plan


SCENARIOS = {
    "Базовий": scenario_baseline,
    "Девальвація": scenario_depreciation,
    "Ревальвація": scenario_appreciation,
}
