"""Engine for the car-plant maintenance & spare-parts system. Standard library only."""
import sqlite3, math, re, calendar, hashlib, secrets, hmac
from datetime import date, timedelta
from pathlib import Path

DB = Path(__file__).parent / "factory.db"

# id, name, production line, criticality(1-5), past failures, vibration mm/s (6 wks), temp C (6 wks),
# days since last PM, PM interval days, usage % of capacity, next-week production load %
MACHINES = [
 ("RW-04","Robotic Welding Arm","Body Assembly",5,3,[2.6,2.6,2.7,2.9,3.1,3.2],[62,63,65,68,71,74],128,90,94,95),
 ("CNC-03","CNC Machining Center","Engine Machining",4,2,[2.0,2.1,2.3,2.4,2.6,2.8],[58,59,60,62,63,65],84,90,88,85),
 ("HP-01","Hydraulic Press 2000T","Body Stamping",5,1,[1.8,1.8,1.9,1.9,2.0,2.0],[55,55,56,57,57,58],80,90,85,82),
 ("CV-08","Assembly Conveyor","Final Assembly",2,0,[1.2,1.2,1.3,1.2,1.2,1.2],[41,41,42,41,42,41],12,90,55,50),
 ("PS-02","Robotic Paint Sprayer","Paint Shop",4,1,[1.5,1.5,1.6,1.6,1.6,1.7],[47,47,48,48,49,49],41,60,78,75),
 ("EA-05","Engine Assembly Station","Powertrain",4,1,[1.7,1.8,1.8,1.9,1.9,2.0],[52,52,53,54,54,55],80,90,84,80),
 ("WT-06","Wheel/Tyre Assembly Machine","Final Assembly",3,0,[1.1,1.1,1.2,1.1,1.2,1.2],[44,44,45,44,45,45],30,90,60,62),
 ("PM-07","Paint Circulation Pump","Paint Shop",3,2,[1.6,1.7,1.9,2.1,2.3,2.5],[50,52,54,57,59,62],76,60,82,70),
 ("MT-09","Conveyor Drive Motor","Body Assembly",3,1,[1.4,1.4,1.5,1.5,1.5,1.6],[60,60,61,61,62,62],48,120,70,65),
 ("CP-10","Plant Air Compressor","Utilities",4,1,[1.9,1.9,2.0,2.0,2.1,2.2],[68,69,70,71,72,74],70,90,90,88),
]
# id, name, vendor, stock, lead time days, safety stock, monthly consumption (6 months), machines using it
PARTS = [
 ("WT-102","Robot Welding Tip","Weldtech Tooling",15,14,10,[18,19,21,22,23,24],["RW-04"]),
 ("SM-21","Servo Motor","Siemens Drives",4,28,2,[2,2,3,3,3,4],["RW-04","PS-02"]),
 ("RG-15","Robot Gear","Fanuc Spares",6,21,3,[3,3,3,4,4,5],["RW-04"]),
 ("B-104","Precision Bearing","SKF Industrial",5,12,8,[12,13,15,15,16,17],["CNC-03","HP-01","EA-05"]),
 ("DB-08","Drive Belt","Gates Belts",17,7,10,[14,13,15,14,15,14],["CNC-03","CV-08"]),
 ("HS-12","Hydraulic Seal","Parker Hannifin",17,10,10,[11,12,12,13,14,15],["CNC-03","HP-01"]),
 ("CR-31","Conveyor Roller","Interroll",90,9,20,[20,21,19,20,22,21],["CV-08"]),
 ("PS-17","Pump Seal","Grundfos Parts",8,15,5,[5,6,7,8,9,10],["PM-07","PS-02"]),
 ("MB-22","Motor Bearing","SKF Industrial",13,12,8,[8,8,9,9,10,10],["MT-09","PM-07","CP-10"]),
 ("AF-05","Compressor Air Filter","Atlas Copco",13,6,8,[9,9,10,9,10,10],["CP-10","PS-02"]),
 ("HH-09","Hydraulic Hose","Parker Hannifin",9,10,6,[6,6,7,7,7,8],["HP-01"]),
 ("CC-40","Compressor Valve Kit","Atlas Copco",3,35,2,[2,2,2,3,3,3],["CP-10"]),
]

def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 60000).hex()

def seed_users(c):
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return
    for u, pw, role in (("admin", "admin123", "admin"), ("viewer", "viewer123", "viewer")):
        salt = secrets.token_hex(8)
        c.execute("INSERT INTO users VALUES(?,?,?,?)", (u, salt, _hash(pw, salt), role))

def check_login(user, pw):
    init_db()
    c = sqlite3.connect(DB)
    r = c.execute("SELECT salt,pw,role FROM users WHERE username=?", (user,)).fetchone()
    c.close()
    return r[2] if r and hmac.compare_digest(_hash(pw, r[0]), r[1]) else None

_ready = False

def init_db():
    global _ready
    if _ready:
        return
    _ready = True
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS machines(id TEXT PRIMARY KEY,name TEXT,line TEXT,crit INT,failures INT,days INT,interval INT,usage INT,load INT);
    CREATE TABLE IF NOT EXISTS readings(machine TEXT,week INT,vib REAL,temp REAL);
    CREATE TABLE IF NOT EXISTS parts(id TEXT PRIMARY KEY,name TEXT,vendor TEXT,stock INT,lead INT,safety INT);
    CREATE TABLE IF NOT EXISTS part_machine(part TEXT,machine TEXT);
    CREATE TABLE IF NOT EXISTS consumption(part TEXT,month INT,qty INT);
    CREATE TABLE IF NOT EXISTS work_orders(machine TEXT,wdate TEXT,type TEXT,status TEXT,note TEXT);
    CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,salt TEXT,pw TEXT,role TEXT);
    """)
    seed_users(c)
    if c.execute("SELECT COUNT(*) FROM machines").fetchone()[0]:
        c.commit(); c.close(); return
    today = date.today()
    for m in MACHINES:
        c.execute("INSERT INTO machines VALUES(?,?,?,?,?,?,?,?,?)", (m[0],m[1],m[2],m[3],m[4],m[7],m[8],m[9],m[10]))
        for w in range(6):
            c.execute("INSERT INTO readings VALUES(?,?,?,?)", (m[0], w, m[5][w], m[6][w]))
        c.execute("INSERT INTO work_orders VALUES(?,?,?,?,?)", (m[0], str(today-timedelta(days=m[7])), "Preventive", "Completed", "Scheduled PM completed"))
        if m[4]:
            c.execute("INSERT INTO work_orders VALUES(?,?,?,?,?)", (m[0], str(today-timedelta(days=m[7]+45)), "Breakdown", "Completed", f"{m[4]} unplanned stop(s) recorded in last 12 months"))
        if m[7] > m[8]:
            c.execute("INSERT INTO work_orders VALUES(?,?,?,?,?)", (m[0], str(today-timedelta(days=m[7]-m[8])), "Preventive", "Overdue", "PM due date passed, not yet executed"))
    for p in PARTS:
        c.execute("INSERT INTO parts VALUES(?,?,?,?,?,?)", p[:6])
        for mid in p[7]:
            c.execute("INSERT INTO part_machine VALUES(?,?)", (p[0], mid))
        for i, q in enumerate(p[6]):
            c.execute("INSERT INTO consumption VALUES(?,?,?)", (p[0], i, q))
    c.commit(); c.close()

def _rows(c, q, a=()):
    cur = c.execute(q, a)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def clamp(x, lo, hi): return max(lo, min(hi, x))
def lvl(score, hi, mid): return "HIGH" if score >= hi else "MEDIUM" if score >= mid else "LOW"

def month_labels():
    t = date.today(); out = []
    for k in range(6, -1, -1):
        m = (t.month - 1 - k) % 12 + 1
        out.append(calendar.month_abbr[m])
    return out[:-1], calendar.month_abbr[(t.month) % 12 + 1]

def _in_scope(m, scen):
    line = scen[1]; kw = scen[2] if len(scen) > 2 else ""
    if line and m["line"] != line: return False
    return not kw or kw in f'{m["id"]} {m["name"]} {m["line"]}'.lower()

def compute(scen=None):
    init_db()
    c = sqlite3.connect(DB)
    ms = _rows(c, "SELECT * FROM machines"); ps = _rows(c, "SELECT * FROM parts")
    links = _rows(c, "SELECT * FROM part_machine")
    labels, nxt = month_labels()
    mmap = {}
    for m in ms:
        if scen and _in_scope(m, scen):  # what-if: production change raises/lowers load, usage and wear
            k = 1 + scen[0] / 100
            m["load"] = min(100, round(m["load"] * k)); m["usage"] = min(100, round(m["usage"] * k)); m["days"] = round(m["days"] * k)
            m["sim"] = True
        r = _rows(c, "SELECT vib,temp FROM readings WHERE machine=? ORDER BY week", (m["id"],))
        r = r[-6:]
        m["vib"] = [x["vib"] for x in r]; m["temp"] = [x["temp"] for x in r]
        m["wos"] = _rows(c, "SELECT wdate,type,status,note FROM work_orders WHERE machine=? ORDER BY wdate DESC", (m["id"],))
        v, t = m["vib"], m["temp"]
        vrise = (v[-1]-v[0])/v[0]*100; trise = t[-1]-t[0]
        f = [
          ("Machine criticality", m["crit"]/5*20, 20),
          ("Failure history", min(m["failures"],4)/4*15, 15),
          ("Vibration trend", clamp(vrise/25,0,1)*20, 20),
          ("Temperature trend", clamp(trise/12,0,1)*8 + (4 if t[-1] >= 70 else 0), 12),
          ("PM overdue", clamp(m["days"]/m["interval"],0,1.5)/1.5*15, 15),
          ("Production usage", m["usage"]/100*8, 8),
          ("Next-week load", m["load"]/100*10, 10),
        ]
        m["factors"] = [{"label": a, "points": round(b,1), "max": d} for a,b,d in f]
        m["score"] = round(sum(x[1] for x in f))
        m["priority"] = lvl(m["score"], 65, 40)
        m["vib_rise"] = round(vrise); m["temp_rise"] = trise
        m["due_in"] = m["interval"] - m["days"]
        R = []
        if m["crit"] >= 4: R.append(f"Critical to the {m['line']} line (criticality {m['crit']}/5)")
        elif m["crit"] <= 2: R.append(f"Low criticality ({m['crit']}/5): line can run around it")
        if vrise >= 10: R.append(f"Vibration up {round(vrise)}% over 6 weeks ({v[0]} to {v[-1]} mm/s)")
        else: R.append(f"Vibration stable at {v[-1]} mm/s")
        if trise >= 6 or t[-1] >= 70: R.append(f"Temperature rising: {t[0]}C to {t[-1]}C")
        else: R.append(f"Temperature normal at {t[-1]}C")
        if m["failures"]: R.append(f"{m['failures']} previous failure(s) recorded")
        else: R.append("No failures on record")
        if m["due_in"] < 0: R.append(f"Preventive maintenance overdue by {-m['due_in']} days")
        else: R.append(f"Last maintenance {m['days']} days ago; next PM due in {m['due_in']} days")
        if m["load"] >= 75: R.append(f"Heavy production schedule next week ({m['load']}% load)")
        else: R.append(f"Normal production load next week ({m['load']}%)")
        m["reasons"] = R
        m["verdict"] = {"HIGH": "HIGH MAINTENANCE PRIORITY: schedule now", "MEDIUM": "MEDIUM PRIORITY: plan in next maintenance window", "LOW": "LOW PRIORITY: no urgent action"}[m["priority"]]
        mmap[m["id"]] = m
    parts = []
    for p in ps:
        hist = [x["qty"] for x in _rows(c, "SELECT qty FROM consumption WHERE part=? ORDER BY month", (p["id"],))]
        used = [mmap[l["machine"]] for l in links if l["part"] == p["id"]]
        wma = 0.2*hist[-3] + 0.3*hist[-2] + 0.5*hist[-1]
        slope = (hist[-1]-hist[0]) / (len(hist)-1)
        avg = sum(u["score"] for u in used)/len(used) if used else 0
        factor = 1 + 0.2*avg/100
        share = sum(1 for u in used if u.get("sim")) / len(used) if used else 0
        scale = 1 + scen[0] / 100 * share if scen else 1  # share of this part's machines affected by the scenario
        demand = math.ceil((wma+slope)*scale*factor)
        daily = demand/30
        lead_use = daily*p["lead"]
        rol = math.ceil(lead_use + p["safety"])
        s = p["stock"]
        risk = "CRITICAL" if (s < rol and s < demand) else "HIGH" if s < rol else "MEDIUM" if s < demand else "LOW"
        qty = max(0, math.ceil(demand + p["safety"] - s)) if risk != "LOW" else 0
        maxcrit = max((u["crit"] for u in used), default=1)
        ps_score = {"CRITICAL":50,"HIGH":35,"MEDIUM":15,"LOW":0}[risk] + maxcrit/5*20 + min(p["lead"],21)/21*15 + avg/100*15
        prio = "LOW" if risk == "LOW" else lvl(ps_score, 60, 35)
        hc = [u for u in used if u["crit"] >= 4]
        R = [f"{len(used)} machine(s) use this part ({', '.join(u['id'] for u in used)}); {len(hc)} high-criticality",
             f"Current stock = {s}",
             f"Predicted next-month demand = {demand} (last 3 months weighted avg {wma:.1f} + trend {slope:+.1f}/month, x{factor:.2f} for machine risk)",
             f"Supplier lead time = {p['lead']} days; expected use during lead time = {lead_use:.1f}",
             f"Reorder level = {rol} (lead-time use + safety stock {p['safety']}); stock is {'below' if s < rol else 'above'} it",
             f"Shortage risk = {risk}"]
        if qty: R.append(f"Recommended reorder quantity = {qty} (demand + safety stock - current stock)")
        parts.append({**p, "hist": hist, "labels": labels, "next": nxt, "demand": demand, "scale": round(scale, 3), "factor": round(factor, 2), "avg_risk": round(avg), "maxcrit": maxcrit,
            "outlook": [max(0, math.ceil((wma + slope*k)*scale*factor)) for k in (1, 2, 3)], "rol": rol,
            "cover_days": round(s/daily) if daily else 999, "risk": risk, "reorder_qty": qty, "priority": prio,
            "pscore": round(ps_score), "machines": [{"id": u["id"], "name": u["name"], "crit": u["crit"], "priority": u["priority"]} for u in used],
            "reasons": R, "action": "Reorder immediately" if risk == "CRITICAL" else "Reorder this week" if risk == "HIGH" else "Plan reorder" if risk == "MEDIUM" else "No action, stock adequate"})
    for m in mmap.values():
        m["parts"] = [{"id": p["id"], "name": p["name"], "risk": p["risk"]} for p in parts if any(x["id"] == m["id"] for x in p["machines"])]
    c.close()
    machines = sorted(mmap.values(), key=lambda m: -m["score"])
    parts.sort(key=lambda p: (-p["pscore"] if p["risk"] != "LOW" else 0, p["id"]))
    return machines, parts, labels, nxt

def alerts(machines, parts):
    out = []
    for p in parts:
        if p["risk"] in ("CRITICAL", "HIGH"):
            out.append({"level": p["risk"], "type": "Spare part shortage", "title": f"{p['name']} {p['id']}: {p['risk']} shortage risk",
                        "detail": f"Stock {p['stock']} vs predicted demand {p['demand']}, lead time {p['lead']} days. {p['action']} (qty {p['reorder_qty']})."})
    for m in machines:
        if m["priority"] == "HIGH":
            out.append({"level": "CRITICAL", "type": "Machine maintenance", "title": f"{m['name']} {m['id']}: HIGH maintenance priority", "detail": m["reasons"][1] + "; " + m["reasons"][4]})
        elif m["due_in"] < 0 or m["priority"] == "MEDIUM":
            out.append({"level": "MEDIUM", "type": "Maintenance", "title": f"{m['name']} {m['id']}: {m['priority']} priority", "detail": m["reasons"][4]})
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    return sorted(out, key=lambda a: order[a["level"]])

def dashboard():
    machines, parts, labels, nxt = compute()
    hi = [m for m in machines if m["priority"] == "HIGH"]
    short = [p for p in parts if p["risk"] in ("CRITICAL", "HIGH")]
    total_hist = [sum(p["hist"][i] for p in parts) for i in range(6)]
    status = "ATTENTION REQUIRED" if len(hi) >= 2 or any(p["risk"] == "CRITICAL" for p in parts) else "WATCH" if hi else "NORMAL"
    return {
      "kpis": {"machines": len(machines), "urgent": len(hi), "high_risk": len([m for m in machines if m["priority"] != "LOW"]),
               "low_stock": len([p for p in parts if p["stock"] < p["rol"]]), "insufficient": len([p for p in parts if p["stock"] < p["demand"]]),
               "upcoming_pm": len([m for m in machines if m["due_in"] <= 30]), "demand_next": sum(p["demand"] for p in parts), "status": status},
      "demand_chart": {"labels": labels + [nxt], "values": total_hist + [sum(p["demand"] for p in parts)]},
      "top_machines": [{k: m[k] for k in ("id","name","line","score","priority")} for m in machines[:5]],
      "upcoming": [{"id": m["id"], "name": m["name"], "due_in": m["due_in"]} for m in sorted(machines, key=lambda m: m["due_in"])[:5]],
      "shortages": [{k: p[k] for k in ("id","name","stock","demand","risk","reorder_qty")} for p in short[:5]],
    }

def _norm(s): return re.sub(r"[\s\-_]", "", s.lower())

def answer(q):
    machines, parts, _, _ = compute()
    n = _norm(q); ql = q.lower()
    for m in machines:
        if _norm(m["id"]) in n or m["name"].lower() in ql:
            return f"{m['name']} {m['id']} ({m['line']}): {m['priority']} priority, risk score {m['score']}/100.\nWhy:\n" + "\n".join("- "+r for r in m["reasons"]) + f"\nTherefore: {m['verdict']}.\nParts used: " + ", ".join(f"{p['id']} ({p['risk']})" for p in m["parts"])
    for p in parts:
        if _norm(p["id"]) in n or p["name"].lower() in ql:
            return f"{p['name']} {p['id']}: shortage risk {p['risk']}, reorder priority {p['priority']}.\nWhy:\n" + "\n".join("- "+r for r in p["reasons"]) + f"\nAction: {p['action']}."
    if re.search(r"\b(hi|hello|hey|thanks|thank you)\b", ql) and len(ql.split()) <= 4:
        return "Hello! I'm the plant maintenance assistant. " + HELP
    if not DOMAIN.search(ql):
        return OUT_OF_DOMAIN
    if re.search(r"\bplan(s|ning)?\b|\baction|recommend|do first|to-?do|criticality|availability", ql):
        return plan_answer()
    if re.search(r"outlook|next (3|three) months|coming months|forecast", ql):
        return outlook_answer()
    if "reorder" in ql or "order" in ql:
        L = [p for p in parts if p["reorder_qty"] > 0]
        return "Reorder this week (highest priority first):\n" + "\n".join(f"- {p['id']} {p['name']}: order {p['reorder_qty']} (stock {p['stock']}, demand {p['demand']}, lead {p['lead']}d) [{p['priority']}]" for p in L) if L else "No reorders needed."
    if "run out" in ql or "shortage" in ql or "stock" in ql or "spare" in ql or "part" in ql:
        L = [p for p in parts if p["risk"] in ("CRITICAL", "HIGH")]
        return "Spare parts likely to run out:\n" + "\n".join(f"- {p['id']} {p['name']}: {p['risk']} (stock {p['stock']}, predicted demand {p['demand']}, lead time {p['lead']}d, {p['cover_days']} days of cover)" for p in L)
    if "failure" in ql or "highest" in ql or "risk" in ql:
        m = machines[0]
        return f"Highest failure risk: {m['name']} {m['id']} with score {m['score']}/100.\n" + "\n".join("- "+r for r in m["reasons"])
    if "maint" in ql or "first" in ql or "priorit" in ql:
        return "Maintenance order (highest risk first):\n" + "\n".join(f"{i+1}. {m['id']} {m['name']}: {m['priority']} (score {m['score']}); {m['reasons'][4]}" for i, m in enumerate(machines[:5]))
    return HELP


# ---------- Editing data (admin) ----------
ID = re.compile(r"^[A-Za-z0-9_-]{2,15}$")

def clean(s): return re.sub(r"[<>&\"'`]", "", str(s)).strip()[:60]

def _db():
    init_db()
    return sqlite3.connect(DB)

def save_machine(d, new):
    d["id"] = str(d["id"]).strip().upper()
    if not ID.match(d["id"]): raise ValueError("Machine ID must be 2-15 letters, digits or hyphens, e.g. RW-05")
    name, line = clean(d["name"]), clean(d["line"])
    if not name or not line: raise ValueError("Machine name and production line are required")
    c = _db()
    try:
        exists = c.execute("SELECT 1 FROM machines WHERE id=?", (d["id"],)).fetchone()
        if new and exists: raise ValueError(f"Machine {d['id']} already exists")
        if not new and not exists: raise LookupError(f"Machine {d['id']} not found")
        v = (name, line, d["crit"], d["failures"], d["days"], d["interval"], d["usage"], d["load"])
        if new:
            c.execute("INSERT INTO machines(id,name,line,crit,failures,days,interval,usage,load) VALUES(?,?,?,?,?,?,?,?,?)", (d["id"],) + v)
            for w in range(6):
                f = w / 5
                c.execute("INSERT INTO readings VALUES(?,?,?,?)", (d["id"], w, round(d["vib_start"] + (d["vib_now"]-d["vib_start"])*f, 2), round(d["temp_start"] + (d["temp_now"]-d["temp_start"])*f, 1)))
            c.execute("INSERT INTO work_orders VALUES(?,?,?,?,?)", (d["id"], str(date.today()-timedelta(days=d["days"])), "Preventive", "Completed", "Last preventive maintenance (entered manually)"))
        else:
            c.execute("UPDATE machines SET name=?,line=?,crit=?,failures=?,days=?,interval=?,usage=?,load=? WHERE id=?", v + (d["id"],))
        c.commit()
    finally:
        c.close()

def delete_machine(mid):
    c = _db()
    try:
        for t in ("readings", "work_orders"): c.execute(f"DELETE FROM {t} WHERE machine=?", (mid,))
        c.execute("DELETE FROM part_machine WHERE machine=?", (mid,))
        c.execute("DELETE FROM machines WHERE id=?", (mid,))
        c.commit()
    finally:
        c.close()

def add_reading(mid, vib, temp):
    c = _db()
    try:
        if not c.execute("SELECT 1 FROM machines WHERE id=?", (mid,)).fetchone(): raise LookupError("Machine not found")
        w = c.execute("SELECT COALESCE(MAX(week),-1)+1 FROM readings WHERE machine=?", (mid,)).fetchone()[0]
        c.execute("INSERT INTO readings VALUES(?,?,?,?)", (mid, w, vib, temp))
        c.commit()
    finally:
        c.close()

def save_part(d, new):
    d["id"] = str(d["id"]).strip().upper()
    if not ID.match(d["id"]): raise ValueError("Part ID must be 2-15 letters, digits or hyphens, e.g. WT-103")
    name, vendor = clean(d["name"]), clean(d["vendor"])
    if not name: raise ValueError("Part name is required")
    try:
        hist = [int(float(x)) for x in str(d["hist"]).replace(";", ",").split(",") if x.strip()]
    except ValueError:
        hist = []
    if len(hist) != 6 or min(hist) < 0: raise ValueError("Monthly consumption needs exactly 6 numbers, oldest first, e.g. 12,13,15,15,16,17")
    ids = [x.strip().upper() for x in str(d["machines"]).split(",") if x.strip()]
    if not ids: raise ValueError("Link at least one machine that uses this part, e.g. RW-04")
    c = _db()
    try:
        for i in ids:
            if not c.execute("SELECT 1 FROM machines WHERE id=?", (i,)).fetchone(): raise ValueError(f"Linked machine {i} does not exist")
        exists = c.execute("SELECT 1 FROM parts WHERE id=?", (d["id"],)).fetchone()
        if new and exists: raise ValueError(f"Part {d['id']} already exists")
        if not new and not exists: raise LookupError(f"Part {d['id']} not found")
        if new:
            c.execute("INSERT INTO parts VALUES(?,?,?,?,?,?)", (d["id"], name, vendor, d["stock"], d["lead"], d["safety"]))
        else:
            c.execute("UPDATE parts SET name=?,vendor=?,stock=?,lead=?,safety=? WHERE id=?", (name, vendor, d["stock"], d["lead"], d["safety"], d["id"]))
            c.execute("DELETE FROM part_machine WHERE part=?", (d["id"],)); c.execute("DELETE FROM consumption WHERE part=?", (d["id"],))
        for i in dict.fromkeys(ids): c.execute("INSERT INTO part_machine VALUES(?,?)", (d["id"], i))
        for k, q in enumerate(hist): c.execute("INSERT INTO consumption VALUES(?,?,?)", (d["id"], k, q))
        c.commit()
    finally:
        c.close()

def delete_part(pid):
    c = _db()
    try:
        for t in ("part_machine", "consumption"): c.execute(f"DELETE FROM {t} WHERE part=?", (pid,))
        c.execute("DELETE FROM parts WHERE id=?", (pid,))
        c.commit()
    finally:
        c.close()


# ---------- What-if production simulator (temporary: never writes to the database) ----------
RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

def _machine_reason(b, s, pct):
    if not s.get("sim"):
        return "Not in the selected production line: unchanged"
    if s["priority"] == b["priority"] and s["priority"] == "LOW":
        return f"Vibration {s['vib'][-1]} mm/s and temperature {s['temp'][-1]}C normal; PM {s['days']} of {s['interval']} days: stays LOW"
    bits = []
    if s["load"] != b["load"]: bits.append(f"next-week load {b['load']}% to {s['load']}%")
    if s["usage"] != b["usage"]: bits.append(f"usage {b['usage']}% to {s['usage']}%")
    if s["days"] != b["days"]: bits.append(f"operating time since last PM {b['days']} to {s['days']} equivalent days (interval {b['interval']})")
    if b["due_in"] >= 0 > s["due_in"]: bits.append("preventive maintenance becomes overdue")
    extra = []
    if b["vib_rise"] >= 10: extra.append(f"existing vibration trend (+{b['vib_rise']}%)")
    if b["failures"]: extra.append(f"{b['failures']} previous failure(s)")
    if b["crit"] >= 4: extra.append(f"criticality {b['crit']}/5")
    txt = f"Score {b['score']} to {s['score']}. Production {pct:+g}%: " + ("; ".join(bits) or "no load change")
    return txt + (". Combined with " + ", ".join(extra) if extra else "")

def _part_reason(b, s, pct):
    n = len([m for m in s["machines"]])
    if RANK[s["risk"]] > RANK[b["risk"]]:
        txt = (f"Production {pct:+g}% raises expected machine usage, increasing consumption of {s['name']}. Predicted demand {b['demand']} to {s['demand']} "
               f"against stock {s['stock']}. Reorder level rises {b['rol']} to {s['rol']} (lead time {s['lead']} days + safety stock {s['safety']}), so current inventory no longer covers it safely.")
    elif RANK[s["risk"]] < RANK[b["risk"]]:
        txt = f"Lower production reduces expected consumption: demand {b['demand']} to {s['demand']}. Stock {s['stock']} now covers the need better."
    elif s["demand"] != b["demand"]:
        txt = f"Demand {b['demand']} to {s['demand']}; risk category unchanged ({s['risk']}). Stock {s['stock']}, reorder level {s['rol']}."
    else:
        return f"Not affected by this scenario (used by machines outside the selected line). Stock {s['stock']}, demand {s['demand']}."
    if s["factor"] != b["factor"]:
        txt += f" Linked machine risk also changed (risk multiplier x{b['factor']} to x{s['factor']})."
    return txt

def _simulate_core(pct, line, kw=""):
    pct = clamp(float(pct), -50, 100); line = (line or "").strip()
    bm, bp, _, _ = compute()
    lines = sorted({m["line"] for m in bm})
    if line and line not in lines: raise ValueError("Unknown production line")
    if kw and not any(_in_scope(m, (0, line, kw)) for m in bm): raise ValueError(f"No machines match '{kw}'")
    sm, sp, _, _ = compute((pct, line, kw))
    B = {m["id"]: m for m in bm}; BP = {p["id"]: p for p in bp}
    def chg(a, b): return "up" if RANK[b] > RANK[a] else "down" if RANK[b] < RANK[a] else "same"
    mrows = [{"id": s["id"], "name": s["name"], "line": s["line"], "before": B[s["id"]]["priority"], "after": s["priority"], "score_before": B[s["id"]]["score"],
              "score_after": s["score"], "change": chg(B[s["id"]]["priority"], s["priority"]), "reason": _machine_reason(B[s["id"]], s, pct)} for s in sm]
    prows = [{"id": s["id"], "name": s["name"], "stock": s["stock"], "demand_before": BP[s["id"]]["demand"], "demand_after": s["demand"], "risk_before": BP[s["id"]]["risk"],
              "risk_after": s["risk"], "reorder_before": BP[s["id"]]["reorder_qty"], "reorder_after": s["reorder_qty"], "change": chg(BP[s["id"]]["risk"], s["risk"]),
              "reason": _part_reason(BP[s["id"]], s, pct)} for s in sp]
    prows.sort(key=lambda r: (-RANK[r["risk_after"]], -(r["demand_after"] - r["demand_before"])))
    mrows.sort(key=lambda r: -r["score_after"])
    def cnt(ps): return sum(1 for p in ps if p["risk"] in ("CRITICAL", "HIGH"))
    def hm(ms): return sum(1 for m in ms if m["priority"] == "HIGH")
    summ = {"production_before": 100, "production_after": round(100 + pct), "demand_before": sum(p["demand"] for p in bp), "demand_after": sum(p["demand"] for p in sp),
            "shortages_before": cnt(bp), "shortages_after": cnt(sp), "high_before": hm(bm), "high_after": hm(sm),
            "reorder_before": sum(p["reorder_qty"] for p in bp), "reorder_after": sum(p["reorder_qty"] for p in sp)}
    lrows = []
    for ln in lines:
        b = [m for m in bm if m["line"] == ln]; s = [m for m in sm if m["line"] == ln]
        lrows.append({"line": ln, "machines": len(b), "in_scope": any(m.get("sim") for m in s), "avg_before": round(sum(m["score"] for m in b)/len(b)), "avg_after": round(sum(m["score"] for m in s)/len(s)),
                      "high_before": hm(b), "high_after": hm(s)})
    return {"pct": pct, "line": (line or "All Lines") + (f" / machines matching '{kw}'" if kw else ""), "lines": lines, "summary": summ, "machines": mrows, "parts": prows, "line_impact": lrows}


NEG = re.compile(r"\b(decreas\w*|drop\w*|reduc\w*|cuts?|fall\w*|fell|lower\w*|down|slow\w*|declin\w*|minus)\b")
STOP = {"machine", "machines"}

def parse_scenario(text):
    """Turn a sentence like 'what if production of robotics increases by 25%' into (pct, line, keyword, note)."""
    t = text.lower()
    n = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:%|percent)?", t)
    if not n: raise ValueError("Include a percentage, e.g. 'production of robotics increases by 25%'")
    val = float(n.group(1))
    pct = -abs(val) if (val < 0 or NEG.search(t)) else abs(val)
    machines = compute()[0]
    line = next((m["line"] for m in machines if m["line"].lower() in t), "")
    kw = ""
    if not line:
        for w in re.findall(r"[a-z]{5,}", t):
            k = w[:5]
            if w in STOP: continue
            if any(k in f'{m["id"]} {m["name"]} {m["line"]}'.lower() for m in machines):
                kw = k; break
    note = []
    if re.search(r"cost|price|budget", t): note.append("The model has no cost data, so a cost change is treated as a workload/production change of that size.")
    if re.search(r"\bto\s+-?\d", t): note.append("'to N' is read as a change of N%.")
    return pct, line, kw, " ".join(note)

def simulate(pct, line="", kw="", text=""):
    note = ""
    if text.strip():
        pct, line, kw, note = parse_scenario(text)
    r = _simulate_core(pct, line, kw)
    r["interpretation"] = f"Interpreted as: production {r['pct']:+g}% for {r['line']}"
    r["note"] = note
    return r


# ---------- Explainable recommendations, planning support, domain guard ----------
HELP = ("I answer from the live plant data. Try: 'Which machines should we maintain first?', 'Which spare parts will run out?', 'Why is RW-04 high priority?', "
        "'What should we reorder this week?', 'Give me an action plan', or 'Demand outlook for the next 3 months'.")
OUT_OF_DOMAIN = ("This question is not in my domain. Please ask anything related to this domain: the car plant's machines, maintenance priorities, spare parts, "
                 "shortages, reorders, demand forecasts, planning, or what-if production scenarios. For example: 'Which machines should we maintain first?'")
DOMAIN = re.compile(r"\b(machines?|machining|maintenance|maintain\w*|spares?|spare parts?|parts|inventory|stock\w*|reorder\w*|suppliers?|vendors?|lead time|shortages?|forecast\w*|"
    r"demand|outlook|vibration|temperature|failures?|production|plant|factory|conveyors?|robots?|robotic\w*|welding|cnc|hydraulic|paint\w*|compressors?|pumps?|motors?|bearings?|"
    r"seals?|belts?|filters?|hoses?|gears?|priorit\w*|urgent|alerts?|simulat\w*|what-if|criticality|availability|downtime|breakdown|equipment|recommend\w*|action plan|"
    r"weekly plan|plan (for|my)|what should we do first|run out)\b")

def _urg(score):
    return ("DO NOW", "HIGH") if score >= 65 else ("THIS WEEK", "MEDIUM") if score >= 40 else ("PLAN", "LOW")

def recommendations():
    """Ranked actions. Score = operational criticality (35) + availability (35) + risk (30), each explained."""
    machines, parts, _, _ = compute()
    recs = []
    for p in parts:
        if p["reorder_qty"] <= 0: continue
        mc, rol, s = p["maxcrit"], max(p["rol"], 1), p["stock"]
        hc = sum(1 for m in p["machines"] if m["crit"] >= 4)
        cp = mc/5*35; ap = clamp((rol - s)/rol, 0, 1)*35
        rp = p["avg_risk"]/100*15 + {"CRITICAL": 1, "HIGH": .7, "MEDIUM": .3, "LOW": 0}[p["risk"]]*15
        score = round(cp + ap + rp); u, ul = _urg(score)
        alvl = "CRITICAL" if p["cover_days"] < p["lead"] else "HIGH" if s < p["rol"] else "MEDIUM" if s < p["demand"] else "LOW"
        dims = {"criticality": {"level": "HIGH" if mc >= 4 else "MEDIUM" if mc == 3 else "LOW", "pts": round(cp), "max": 35,
                                "detail": f"Used by {len(p['machines'])} machine(s), {hc} high-criticality; highest criticality {mc}/5"},
                "availability": {"level": alvl, "pts": round(ap), "max": 35,
                                 "detail": f"Stock {s} = {p['cover_days']} days of cover vs {p['lead']} days supplier lead time; reorder level {p['rol']}"},
                "risk": {"level": lvl(rp, 20, 10), "pts": round(rp), "max": 30,
                         "detail": f"Shortage risk {p['risk']}; linked machines average risk score {p['avg_risk']}/100; predicted demand {p['demand']}"}}
        action = f"Reorder {p['reorder_qty']} x {p['id']} {p['name']} ({p['vendor']}, lead time {p['lead']} days)"
        why = [dims[k]["detail"] for k in dims] + [f"Therefore: {u}. Order now so stock covers demand plus safety stock ({p['safety']})."]
        recs.append({"kind": "reorder", "id": p["id"], "action": action, "urgency": u, "urgency_level": ul, "score": score, "dims": dims, "why": why})
    for m in machines:
        if m["priority"] == "LOW": continue
        short = [x for x in m["parts"] if x["risk"] in ("CRITICAL", "HIGH")]
        share = len(short)/len(m["parts"]) if m["parts"] else 0
        cp = m["crit"]/5*35; ap = share*35; rp = m["score"]/100*30
        score = round(cp + ap + rp); u, ul = _urg(score)
        alvl = "LOW" if share == 0 else "MEDIUM" if share < .5 else "HIGH" if share < 1 else "CRITICAL"
        dims = {"criticality": {"level": "HIGH" if m["crit"] >= 4 else "MEDIUM" if m["crit"] == 3 else "LOW", "pts": round(cp), "max": 35,
                                "detail": f"Criticality {m['crit']}/5 on the {m['line']} line; {m['load']}% production load next week"},
                "availability": {"level": alvl, "pts": round(ap), "max": 35,
                                 "detail": (f"{len(short)} of {len(m['parts'])} spare parts are short ({', '.join(x['id'] for x in short)}); secure them before the maintenance window" if short else "All spare parts needed for this machine are in stock")},
                "risk": {"level": m["priority"], "pts": round(rp), "max": 30, "detail": f"Risk score {m['score']}/100. {m['reasons'][1]}; {m['reasons'][4]}"}}
        action = f"Schedule maintenance on {m['id']} {m['name']}" + (f" (order {', '.join(x['id'] for x in short)} first)" if short else " (spares in stock)")
        why = [dims[k]["detail"] for k in dims] + [f"Therefore: {u}."]
        recs.append({"kind": "maintain", "id": m["id"], "action": action, "urgency": u, "urgency_level": ul, "score": score, "dims": dims, "why": why})
    recs.sort(key=lambda r: -r["score"])
    t = date.today()
    months = [calendar.month_abbr[(t.month - 1 + k) % 12 + 1] for k in (1, 2, 3)]
    rows = sorted(({"id": p["id"], "name": p["name"], "months": p["outlook"], "total": sum(p["outlook"]), "stock": p["stock"], "risk": p["risk"]} for p in parts), key=lambda r: -r["total"])
    return {"recommendations": recs, "months": months, "totals": [sum(p["outlook"][k] for p in parts) for k in range(3)], "outlook": rows,
            "summary": {"do_now": sum(r["urgency"] == "DO NOW" for r in recs), "this_week": sum(r["urgency"] == "THIS WEEK" for r in recs), "plan": sum(r["urgency"] == "PLAN" for r in recs)}}

def plan_answer():
    d = recommendations(); L = ["Action plan, ranked by operational criticality, availability and risk:"]
    for i, r in enumerate(d["recommendations"][:6], 1):
        x = r["dims"]
        L.append(f"{i}. [{r['urgency']}] {r['action']} (score {r['score']}/100)\n   Criticality: {x['criticality']['detail']}\n   Availability: {x['availability']['detail']}\n   Risk: {x['risk']['detail']}")
    L.append(f"Demand outlook: {', '.join(f'{m} {v}' for m, v in zip(d['months'], d['totals']))} units in total. Open the Recommendations page for full explanations.")
    return "\n".join(L)

def outlook_answer():
    d = recommendations(); rows = sorted(d["outlook"], key=lambda r: -(r["months"][2] - r["months"][0]))[:5]
    return (f"Spare-part demand outlook: {', '.join(f'{m} {v}' for m, v in zip(d['months'], d['totals']))} units in total.\nFastest-growing parts:\n"
            + "\n".join(f"- {r['id']} {r['name']}: {r['months'][0]} to {r['months'][1]} to {r['months'][2]} units (stock {r['stock']}, risk {r['risk']})" for r in rows))
