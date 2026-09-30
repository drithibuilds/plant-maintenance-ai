import secrets
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import engine

app = FastAPI(title="Car Plant Maintenance AI")
engine.init_db()
STATIC = Path(__file__).parent / "static"
SESSIONS = {}  # token -> {"username", "role"}  (in memory: restarting the server signs everyone out)

# ---------- auth ----------
def current_user(authorization: Optional[str] = Header(None)):
    token = (authorization or "").replace("Bearer ", "")
    if token not in SESSIONS:
        raise HTTPException(401, "Not signed in")
    return SESSIONS[token]

def admin_only(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Only the admin role can change data")
    return user

def run(fn, *args):
    try:
        return fn(*args)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))

def dump(m):
    return m.model_dump() if hasattr(m, "model_dump") else m.dict()

# ---------- request models ----------
class Login(BaseModel):
    username: str
    password: str

class MachineIn(BaseModel):
    id: str
    name: str
    line: str
    crit: int = Field(..., ge=1, le=5)
    failures: int = Field(..., ge=0, le=100)
    days: int = Field(..., ge=0, le=3650)
    interval: int = Field(..., ge=1, le=3650)
    usage: int = Field(..., ge=0, le=100)
    load: int = Field(..., ge=0, le=100)

class MachineNew(MachineIn):
    vib_start: float = Field(..., gt=0)
    vib_now: float = Field(..., gt=0)
    temp_start: float
    temp_now: float

class Reading(BaseModel):
    vib: float = Field(..., gt=0)
    temp: float

class PartIn(BaseModel):
    id: str
    name: str
    vendor: str = ""
    stock: int = Field(..., ge=0)
    lead: int = Field(..., ge=1, le=365)
    safety: int = Field(..., ge=0)
    hist: str
    machines: str

class Chat(BaseModel):
    question: str

# ---------- public ----------
@app.post("/api/login")
def login(b: Login):
    role = engine.check_login(b.username.strip(), b.password)
    if not role:
        raise HTTPException(401, "Invalid username or password")
    token = secrets.token_hex(16)
    SESSIONS[token] = {"username": b.username.strip(), "role": role}
    return {"token": token, "role": role, "username": b.username.strip()}

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")

# ---------- read (any signed-in user) ----------
@app.get("/api/dashboard")
def dashboard(u=Depends(current_user)): return engine.dashboard()

@app.get("/api/machines")
def machines(u=Depends(current_user)): return engine.compute()[0]

@app.get("/api/parts")
def parts(u=Depends(current_user)): return engine.compute()[1]

@app.get("/api/alerts")
def alerts(u=Depends(current_user)):
    m, p, _, _ = engine.compute()
    return engine.alerts(m, p)

@app.get("/api/recommendations")
def recommendations(u=Depends(current_user)): return engine.recommendations()

@app.post("/api/chat")
def chat(body: Chat, u=Depends(current_user)):
    return {"answer": engine.answer(body.question), "source": "local-engine"}

# ---------- write (admin only) ----------
@app.post("/api/machines")
def machine_add(d: MachineNew, u=Depends(admin_only)):
    run(engine.save_machine, dump(d), True); return {"ok": True}

@app.put("/api/machines/{mid}")
def machine_edit(mid: str, d: MachineIn, u=Depends(admin_only)):
    data = dump(d); data["id"] = mid
    run(engine.save_machine, data, False); return {"ok": True}

@app.delete("/api/machines/{mid}")
def machine_delete(mid: str, u=Depends(admin_only)):
    run(engine.delete_machine, mid); return {"ok": True}

@app.post("/api/machines/{mid}/readings")
def machine_reading(mid: str, r: Reading, u=Depends(admin_only)):
    run(engine.add_reading, mid, r.vib, r.temp); return {"ok": True}

@app.post("/api/parts")
def part_add(d: PartIn, u=Depends(admin_only)):
    run(engine.save_part, dump(d), True); return {"ok": True}

@app.put("/api/parts/{pid}")
def part_edit(pid: str, d: PartIn, u=Depends(admin_only)):
    data = dump(d); data["id"] = pid
    run(engine.save_part, data, False); return {"ok": True}

@app.delete("/api/parts/{pid}")
def part_delete(pid: str, u=Depends(admin_only)):
    run(engine.delete_part, pid); return {"ok": True}

# ---------- what-if simulator (read-only: never changes stored data) ----------
@app.get("/api/simulate")
def simulate(pct: float = 20, line: str = "", kw: str = "", text: str = "", u=Depends(current_user)):
    return run(engine.simulate, pct, line, kw, text)
