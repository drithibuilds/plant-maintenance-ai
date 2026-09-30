# Car Plant Maintenance & Spare-Parts AI (hackathon prototype)

FastAPI + SQLite backend, single-page dashboard (no npm/build step). Works offline, no API key needed.

## Run (Windows)
    cd plant-maintenance-ai
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    uvicorn main:app --port 8000

## Run (Mac/Linux)
    cd plant-maintenance-ai
    python3 -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    uvicorn main:app --port 8000

Open http://localhost:8000. The database (factory.db) and synthetic data are created automatically on first start. Delete factory.db to reset.

## Demo scenarios
1. Machine Maintenance > RW-04 Robotic Welding Arm: HIGH (score 93), with reasons.
2. Spare Parts > B-104 Precision Bearing: CRITICAL shortage, reorder 23. Also WT-102 welding tip.
3. Machine Maintenance > CV-08 Assembly Conveyor: LOW, no urgent action; CR-31 rollers stock adequate.
4. AI Assistant: click the suggested questions.

## Files
engine.py (data, scoring, forecast, explanations, assistant) | main.py (API routes) | static/index.html (UI)
API: /api/dashboard /api/machines /api/parts /api/alerts POST /api/chat

## Login and editing data
Sign in with **admin / admin123** (can add, edit, delete) or **viewer / viewer123** (read only).
- Machine Maintenance page: "+ Add machine"; click a machine for Edit, Add sensor reading, Delete.
- Spare Parts page: "+ Add spare part"; click a part for Edit (stock, lead time, consumption history, linked machines) or Delete.
All scores, forecasts, alerts and assistant answers recalculate instantly from the edited data.
Upgrading from the previous zip: delete factory.db once, then restart.

## What-If Simulator
Sidebar > What-If Simulator. Pick a production change (-20% to +30%) and optionally one production line, then RUN SIMULATION.
It recalculates machine load/usage/wear, part demand, shortage risk, reorder quantity and priorities using the same engine, and explains every change. Nothing is saved; "Reset Simulation" clears it.
API: GET /api/simulate?pct=20&line=Paint%20Shop
Demo data was tuned so +20% visibly tips parts into shortage. IMPORTANT: delete factory.db once and restart to load the tuned data.
Demo flow: Dashboard, then What-If Simulator, +20%, RUN SIMULATION (demand 167 to 198, shortages 6 to 8, reorder 77 to 133, CP-10 MEDIUM to HIGH), then Reset.

### Custom scenarios (What-If Simulator)
- Type any % (-50 to 100) in "enter your own % change", or write a sentence, e.g. "What if production of robotics increases by 25%?", "paint shop production drops 15%", "welding workload up 30%".
- The sentence is parsed locally (no API): number = % change, words like drops/reduces = negative, a production line name or a machine word (robotic, welding, conveyor, pump...) = scope. The interpretation is shown above the results.
- The model has no cost data, so a "cost" change is treated as a workload change of that size (a note says so).

## Planning & Recommendations page
Sidebar > Planning & Recommendations. Every action (reorder a part / maintain a machine) is scored out of 100 on three explained dimensions:
operational criticality (35), availability (35: stock vs reorder level, days of cover vs supplier lead time, or missing spares for a machine) and risk (30).
Urgency: DO NOW (65+), THIS WEEK (40-64), PLAN (below 40). The page also shows a 3-month demand outlook and a plain-language planning box.
API: GET /api/recommendations

## Assistant domain guard
Questions unrelated to the plant get: "This question is not in my domain. Please ask anything related to this domain..."
New assistant questions: "Give me an action plan", "What should we do first?", "Demand outlook for the next 3 months".
