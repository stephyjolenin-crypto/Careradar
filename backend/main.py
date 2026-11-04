import math
import json
import os
import time
from typing import Optional
from datetime import datetime, timezone

import httpx
from supabase import create_client
from dotenv import load_dotenv
from google import genai
from google.genai import types
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
load_dotenv(override=True)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", "").strip())
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OSRM = "https://router.project-osrm.org"
VALID_TYPES = ("cardiac", "stroke", "accident", "pregnancy")

sb = None
try:
    sb = create_client(os.getenv("SUPABASE_URL", "").strip(), os.getenv("SUPABASE_KEY", "").strip())
except Exception as e:
    print("Supabase error:", e)

# Backup demo data, used only if Supabase cannot be reached.
HOSPITALS = [
    {"id": 1, "name": "Chettinad Health City", "lat": 12.7957, "lng": 80.2231,
     "specialties": ["cardiac", "stroke", "accident", "pregnancy"],
     "has_ct": True, "has_trauma": True, "icu_free": 4, "beds_free": 22, "minutes_old": 3},
    {"id": 2, "name": "Apollo Speciality OMR", "lat": 12.9066, "lng": 80.2299,
     "specialties": ["cardiac", "accident", "pregnancy"],
     "has_ct": True, "has_trauma": False, "icu_free": 2, "beds_free": 9, "minutes_old": 6},
    {"id": 3, "name": "MIOT International", "lat": 13.0226, "lng": 80.1851,
     "specialties": ["cardiac", "stroke", "accident"],
     "has_ct": True, "has_trauma": True, "icu_free": 1, "beds_free": 12, "minutes_old": 4},
    {"id": 4, "name": "Fortis Malar Adyar", "lat": 13.0067, "lng": 80.2570,
     "specialties": ["cardiac", "stroke", "pregnancy"],
     "has_ct": True, "has_trauma": False, "icu_free": 5, "beds_free": 14, "minutes_old": 52},
]

# Weights: (closeness, availability, specialty match, fresh data)
WEIGHTS = {
    "cardiac": (0.30, 0.30, 0.25, 0.15),
    "stroke": (0.35, 0.20, 0.30, 0.15),
    "accident": (0.35, 0.25, 0.25, 0.15),
    "pregnancy": (0.25, 0.30, 0.30, 0.15),
}

# ---------- hospital data (cached for 3 seconds) ----------
_cache = {"time": 0.0, "data": None}


def get_hospitals():
    """Read hospitals from Supabase. If anything fails, use the demo list."""
    if sb:
        if _cache["data"] and time.time() - _cache["time"] < 3:
            return _cache["data"]
        try:
            rows = sb.table("hospitals").select("*").execute().data
            if rows:
                now = datetime.now(timezone.utc)
                out = []
                for r in rows:
                    age = 0
                    if r.get("updated_at"):
                        t = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
                        age = max(0, int((now - t).total_seconds() / 60))
                    out.append({
                        "id": r["id"],
                        "name": r.get("name", "Hospital"),
                        "lat": float(r["lat"]),
                        "lng": float(r["lng"]),
                        "phone": r.get("phone"),
                        "specialties": r.get("specialties") or [],
                        "has_ct": bool(r.get("has_ct")),
                        "has_trauma": bool(r.get("has_trauma")),
                        "icu_free": int(r.get("icu_free") or 0),
                        "beds_free": int(r.get("beds_free") or 0),
                        "minutes_old": age,
                    })
                _cache["data"] = out
                _cache["time"] = time.time()
                return out
        except Exception as e:
            print("Supabase read error:", e)
    return HOSPITALS


# ---------- distance and road travel time ----------
def distance_km(lat1, lng1, lat2, lng2):
    r = math.radians
    a = (math.sin(r(lat2 - lat1) / 2) ** 2
         + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lng2 - lng1) / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


_road_cache = {}


def road_times(lat, lng, hospitals):
    """Driving time in seconds from the patient to each hospital (one OSRM call).
    Returns None if OSRM is slow or fails, so the caller can use an estimate."""
    if not hospitals:
        return None
    key = (round(lat, 3), round(lng, 3), tuple(h["id"] for h in hospitals))
    hit = _road_cache.get(key)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    try:
        # OSRM wants longitude FIRST, then latitude
        coords = f"{lng},{lat};" + ";".join(f"{h['lng']},{h['lat']}" for h in hospitals)
        r = httpx.get(
            f"{OSRM}/table/v1/driving/{coords}",
            params={"sources": "0", "annotations": "duration"},
            timeout=4.0,
        )
        data = r.json()
        if data.get("code") == "Ok":
            result = data["durations"][0][1:]
            if len(_road_cache) > 200:
                _road_cache.clear()
            _road_cache[key] = (time.time(), result)
            return result
    except Exception as e:
        print("OSRM table error:", e)
    return None


def make_reasons(t, h, eta, resource, eta_source):
    """Short sentences that are true for this hospital. Nothing is invented."""
    reasons = []
    bed_name = "ICU" if t in ("cardiac", "stroke") else "general"
    if resource > 0:
        reasons.append(f"{resource} {bed_name} bed(s) free")
    else:
        reasons.append(f"No {bed_name} beds free right now")
    way = "by road" if eta_source == "road" else "(estimate)"
    reasons.append(f"About {eta} min away {way}")
    if t in h["specialties"]:
        reasons.append(f"Treats {t} cases")
    if t == "stroke" and h["has_ct"]:
        reasons.append("CT scanner available")
    if t == "accident" and h["has_trauma"]:
        reasons.append("Trauma care available")
    age = h["minutes_old"]
    if age <= 15:
        reasons.append(f"Bed data updated {age} min ago")
    else:
        reasons.append(f"Bed data is {age} min old")
    return reasons


# ---------- basic pages ----------
@app.get("/")
def home():
    return {"app": "CareRadar API", "status": "running", "docs": "/docs"}


@app.get("/health")
def health():
    return {
        "ok": True,
        "supabase": sb is not None,
        "gemini": bool(os.getenv("GEMINI_API_KEY", "").strip()),
    }


# ---------- ranking ----------
class RankRequest(BaseModel):
    lat: float
    lng: float
    type: str
    exclude: list[int] = []  # hospital ids to skip, e.g. one that diverted


@app.post("/rank")
def rank(req: RankRequest):
    if req.type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail="type must be cardiac, stroke, accident or pregnancy")
    w = WEIGHTS[req.type]
    hospitals = [h for h in get_hospitals() if h["id"] not in req.exclude]
    times = road_times(req.lat, req.lng, hospitals)
    results = []
    for i, h in enumerate(hospitals):
        km = distance_km(req.lat, req.lng, h["lat"], h["lng"])
        if times and times[i] is not None:
            eta = max(1, round(times[i] / 60))
            eta_source = "road"
        else:
            eta = round(km * 1.4 / 28 * 60)  # rough minutes by road
            eta_source = "estimate"
        resource = h["icu_free"] if req.type in ("cardiac", "stroke") else h["beds_free"]

        spec = 0.6 if req.type in h["specialties"] else 0
        if req.type == "stroke" and h["has_ct"]:
            spec += 0.4
        if req.type == "accident" and h["has_trauma"]:
            spec += 0.4
        if req.type == "pregnancy":
            spec += 0.4

        close = max(0, 1 - eta / 60)
        avail = min(resource / 4, 1)
        fresh = max(0, 1 - h["minutes_old"] / 60)
        score = w[0] * close + w[1] * avail + w[2] * min(spec, 1) + w[3] * fresh
        if resource == 0:
            score *= 0.4  # no free bed: push it down the list

        results.append({
            "hospital": h,
            "score": round(score * 100),
            "eta_min": eta,
            "eta_source": eta_source,
            "age_min": h["minutes_old"],
            "reasons": make_reasons(req.type, h, eta, resource, eta_source),
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


# ---------- route line for the map ----------
class Point(BaseModel):
    lat: float
    lng: float


class RouteRequest(BaseModel):
    origin: Point
    destination: Point


@app.post("/route")
def route(req: RouteRequest):
    a, b = req.origin, req.destination
    try:
        url = f"{OSRM}/route/v1/driving/{a.lng},{a.lat};{b.lng},{b.lat}"
        r = httpx.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=5.0)
        data = r.json()
        if data.get("code") == "Ok":
            best = data["routes"][0]
            # OSRM gives [lng, lat]; Leaflet wants [lat, lng]
            line = [[lat, lng] for lng, lat in best["geometry"]["coordinates"]]
            return {
                "minutes": max(1, round(best["duration"] / 60)),
                "km": round(best["distance"] / 1000, 1),
                "line": line,
                "source": "road",
            }
    except Exception as e:
        print("OSRM route error:", e)
    km = distance_km(a.lat, a.lng, b.lat, b.lng)
    return {
        "minutes": round(km * 1.4 / 28 * 60),
        "km": round(km, 1),
        "line": [[a.lat, a.lng], [b.lat, b.lng]],
        "source": "estimate",
    }


# ---------- two-way alerts ----------
ALERTS = {}  # backup copy in memory, key = alert id
_memory_id = [0]  # memory-only alerts get negative ids so they never clash


class AlertRequest(BaseModel):
    hospital_id: int
    type: str
    eta_min: int
    summary: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str


@app.post("/alert")
def alert(req: AlertRequest):
    if req.type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail="type must be cardiac, stroke, accident or pregnancy")
    record = {
        "hospital_id": req.hospital_id,
        "emergency_type": req.type,
        "eta_min": req.eta_min,
        "status": "sent",
        "summary": req.summary,
    }
    if sb:
        try:
            saved = sb.table("alerts").insert(record).execute().data[0]
            ALERTS[saved["id"]] = saved
            return {"ok": True, "id": saved["id"], "status": "sent"}
        except Exception as e:
            print("Supabase alert error:", e)
    _memory_id[0] -= 1
    mem = {**record, "id": _memory_id[0], "created_at": datetime.now().isoformat()}
    ALERTS[mem["id"]] = mem
    return {"ok": True, "id": mem["id"], "status": "sent"}


@app.get("/alert/{alert_id}")
def get_alert(alert_id: int):
    if sb and alert_id > 0:
        try:
            rows = sb.table("alerts").select("*").eq("id", alert_id).execute().data
            if rows:
                return rows[0]
        except Exception as e:
            print("Supabase alert read error:", e)
    if alert_id in ALERTS:
        return ALERTS[alert_id]
    raise HTTPException(status_code=404, detail="Alert not found")


@app.patch("/alert/{alert_id}")
def update_alert(alert_id: int, body: StatusUpdate):
    if body.status not in ("accepted", "diverted"):
        raise HTTPException(status_code=400, detail="status must be accepted or diverted")
    if sb and alert_id > 0:
        try:
            rows = sb.table("alerts").update({"status": body.status}).eq("id", alert_id).execute().data
            if rows:
                return {"ok": True, "id": alert_id, "status": body.status}
        except Exception as e:
            print("Supabase alert update error:", e)
    if alert_id in ALERTS:
        ALERTS[alert_id]["status"] = body.status
        return {"ok": True, "id": alert_id, "status": body.status}
    raise HTTPException(status_code=404, detail="Alert not found")


@app.get("/alerts/{hospital_id}")
def alerts_for_hospital(hospital_id: int):
    if sb:
        try:
            return (
                sb.table("alerts").select("*").eq("hospital_id", hospital_id)
                .order("created_at", desc=True).limit(20).execute().data
            )
        except Exception as e:
            print("Supabase alerts error:", e)
    return [a for a in ALERTS.values() if a["hospital_id"] == hospital_id]


# ---------- triage (unchanged for now; we upgrade it in the next part) ----------
# Person 4 will improve this prompt. Edit only the text between the quotes.
TRIAGE_PROMPT = """You are an emergency triage assistant for hospitals in India.
The user describes a medical problem in Tamil, Hindi or English.
Reply ONLY with JSON, no other text, in this exact format:
{"type": "cardiac|stroke|accident|pregnancy", "urgency": "critical|urgent|routine", "message": "one short sentence in the user's own language telling them what kind of hospital to go to. If urgency is critical, tell them to call 108."}
This is guidance only, not a diagnosis."""


class TriageRequest(BaseModel):
    text: str
    lang: str = "en"


def keyword_fallback(text):
    t = text.lower()
    if any(w in t for w in ["chest", "heart", "நெஞ்சு", "सीने", "दिल"]):
        return "cardiac"
    if any(w in t for w in ["stroke", "பக்கவாதம்", "लकवा", "slur", "face"]):
        return "stroke"
    if any(w in t for w in ["pregnan", "labour", "labor", "கர்ப்ப", "गर्भ"]):
        return "pregnancy"
    return "accident"


MODELS = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite"]  # use names from your own model list


@app.post("/triage")
def triage(req: TriageRequest):
    for model in MODELS:
        for attempt in range(2):
            try:
                reply = client.models.generate_content(
                    model=model,
                    contents=req.text,
                    config=types.GenerateContentConfig(
                        system_instruction=TRIAGE_PROMPT,
                        response_mime_type="application/json",
                        max_output_tokens=1000,
                    ),
                )
                data = json.loads(reply.text.strip())
                if data.get("type") in VALID_TYPES:
                    return data
            except Exception as e:
                print("Triage error:", model, e)
                time.sleep(1.5)
    return {
        "type": keyword_fallback(req.text),
        "urgency": "urgent",
        "message": "Go to the top-ranked hospital. Call 108 if the person is struggling to breathe or unresponsive.",
    }