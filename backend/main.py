import math
import json
import os
import time
from datetime import datetime, timezone
from supabase import create_client
from dotenv import load_dotenv
from google import genai
from google.genai import types
from fastapi import FastAPI
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


def get_hospitals():
    """Read hospitals from Supabase. If anything fails, use the demo list."""
    if sb:
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
                        "specialties": r.get("specialties") or [],
                        "has_ct": bool(r.get("has_ct")),
                        "has_trauma": bool(r.get("has_trauma")),
                        "icu_free": int(r.get("icu_free") or 0),
                        "beds_free": int(r.get("beds_free") or 0),
                        "minutes_old": age,
                    })
                return out
        except Exception as e:
            print("Supabase read error:", e)
    return HOSPITALS


class RankRequest(BaseModel):
    lat: float
    lng: float
    type: str


def distance_km(lat1, lng1, lat2, lng2):
    r = math.radians
    a = (math.sin(r(lat2 - lat1) / 2) ** 2
         + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lng2 - lng1) / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


@app.get("/")
def home():
    return {"app": "CareRadar API", "status": "running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/rank")
def rank(req: RankRequest):
    w = WEIGHTS.get(req.type, WEIGHTS["cardiac"])
    results = []
    for h in get_hospitals():
        km = distance_km(req.lat, req.lng, h["lat"], h["lng"])
        eta = round(km * 1.4 / 28 * 60)  # rough minutes by road
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
            "age_min": h["minutes_old"],
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


ALERTS = []  # kept in memory as a backup copy


class AlertRequest(BaseModel):
    hospital_id: int
    type: str
    eta_min: int


@app.post("/alert")
def alert(req: AlertRequest):
    record = {
        "hospital_id": req.hospital_id,
        "emergency_type": req.type,
        "eta_min": req.eta_min,
    }
    ALERTS.append({**record, "type": req.type, "created_at": datetime.now().isoformat()})
    if sb:
        try:
            sb.table("alerts").insert(record).execute()
        except Exception as e:
            print("Supabase alert error:", e)
    return {"ok": True}


@app.get("/alerts/{hospital_id}")
def alerts_for_hospital(hospital_id: int):
    return [a for a in ALERTS if a["hospital_id"] == hospital_id]


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
                if data.get("type") in ("cardiac", "stroke", "accident", "pregnancy"):
                    return data
            except Exception as e:
                print("Triage error:", model, e)
                time.sleep(1.5)
    return {
        "type": keyword_fallback(req.text),
        "urgency": "urgent",
        "message": "Go to the top-ranked hospital. Call 108 if the person is struggling to breathe or unresponsive.",
    }
    

