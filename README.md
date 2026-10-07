# NBU University Challenge 2026 — рекомендації щодо монетарної політики

Квартальна прогнозна модель НБУ (QPM), перенесена з MATLAB/IRIS на Python і звірена з оригіналом, з автоматичним оновленням даних, короткостроковим прогнозом інфляції, сценаріями, аналізом варіантів політики та презентацією, що збирається з результатів моделі.

**Терміни:** подача — 28.10.2026, засідання Правління НБУ — 29.10.2026, фінал — 26.11.2026 ([сайт конкурсу](https://events.bank.gov.ua/uchallenge2026/)).

## Результат

| | |
|---|---|
| Презентація | [`presentation/NBU_University_Challenge_2026.pptx`](presentation/NBU_University_Challenge_2026.pptx) (+ `.pdf`) — 31 слайд з нотатками доповідача |
| Підсумки прогнозу | [`docs/forecast_summary.md`](docs/forecast_summary.md) |
| Припущення і судження | [`docs/assumptions.md`](docs/assumptions.md) |
| Методологія | [`docs/methodology.md`](docs/methodology.md) |
| Підготовка до запитань журі | [`docs/qa_prep.md`](docs/qa_prep.md) |
| Як оновлювати до дедлайну й фіналу | [`docs/update_guide.md`](docs/update_guide.md) |
| Звірка з MATLAB/IRIS | [`docs/matlab_check.md`](docs/matlab_check.md) — максимальна розбіжність ~1e−5 |
| Факти й джерела | [`docs/research_notes.md`](docs/research_notes.md), [`data/UPDATE_LOG.md`](data/UPDATE_LOG.md) |

**Рекомендація (базовий варіант):** підвищити облікову ставку на 0,5 в. п. до 16,5% та утримувати щонайменше до кінця I кв. 2027; керована гнучкість курсу (поступове послаблення гривні до євро ≈4% у 2027 замість витрачання ≈$5 млрд резервів на місяць); пауза в наступних кроках валютної лібералізації до відновлення резервів і ритму допомоги.

## Швидкий старт

```bash
python -m pip install -r requirements.txt
cd deck && npm install && cd ..
python build.py --fetch      # дані → графіки → прогноз → документи → презентація → PDF → тести
```

`python build.py` без `--fetch` перебудовує все з уже завантажених даних. PDF експортується через встановлений PowerPoint (`deck/export.ps1`).

## Структура

| Шлях | Що це |
|---|---|
| `model/model.model` | Рівняння моделі — той самий файл, що в шаблоні НБУ (синтаксис IRIS) |
| `model/params.yaml` | Параметри і стандартні відхилення шоків |
| `config.py` | Дати, короткостроковий прогноз, судження, курсова траєкторія, сценарії, варіанти рішення, рекомендація |
| `update_data.py` | Дані моделі з API НБУ / ЄЦБ / Eurostat + звірка з шаблоном |
| `make_overview_charts.py` | Дані й графіки для огляду економіки (`qpm/overview.py`) |
| `run_forecast.py` | Фільтр, прогноз, сценарії, варіанти політики, оптимальна траєкторія, віяло, бектест, резерви |
| `run_irfs.py` | Функції відгуку на шоки |
| `make_docs.py` | Генерує `docs/assumptions.md`, `docs/forecast_summary.md` |
| `deck/content.py`, `deck/build_deck.js` | Зміст і верстка презентації; всі цифри — з `results/key_numbers.json` |
| `qpm/` | Рушій: парсер `.model`, розв'язувач (Sims gensys), фільтр Калмана, симуляції з планом, наукаст, оптимальна політика, невизначеність, бектест, резерви, читання файлів НБУ |
| `matlab/` | Звірка з оригінальною моделлю в MATLAB/IRIS |
| `nbu_template/` | Оригінальний шаблон НБУ (MATLAB) — не змінюємо |
| `tests/` | `python -m pytest -q` |

## Відповідність MATLAB-шаблону

| MATLAB / IRIS | Python |
|---|---|
| `a01_read_data.m` | `qpm/data.py::read_data` (STL замість X-13) |
| `Model.fromFile`, `solve` | `qpm/model.py::Model` (QZ / gensys) |
| `filter` | `qpm/kalman.py::kalman_smoother` |
| `plan`, `exogenize`, `endogenize`, `jforecast(..., 'anticipate', true)` | `qpm/simulate.py::Plan`, `forecast` |
| `srf` (`b02_irfs.m`) | `qpm/simulate.py::irf` |

### Звірка з MATLAB

```bash
python matlab/export_inputs.py
matlab -batch "addpath('<шлях до IRIS>'); iris.startup('silent',true); cd('matlab'); run_check"
python matlab/compare_with_matlab.py
```

На тих самих даних і плані прогнозу фільтр і прогноз Python збігаються з MATLAB R2026b + IRIS 20230622 до ~1e−5 (див. `docs/matlab_check.md`).

## Тести

- рівняння моделі виконуються на розв'язку (~1e−13), умови Бланшара–Кана;
- функції відгуку збігаються з MATLAB-результатами шаблону;
- фільтр відтворює спостережувані дані;
- план прогнозу точно потрапляє у фіксовані значення;
- цифри на слайді «Головне» = результати моделі;
- (якщо є результати MATLAB) прогноз Python = прогноз IRIS.
