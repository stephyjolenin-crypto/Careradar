import math
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fake demo data. Person 2's database will replace this later.
HOSPITALS = [
    {"id": 1, "name": "Chettinad Health City", "lat": 12.7957, "lng": 80.2231,
     "specialties": ["cardiac", "stroke", "accident", "pregnancy"],
     "has_ct": True, "has_trauma": True, "icu_free": 0, "beds_free": 22, "minutes_old": 3},
    {"id": 2, "name": "Apollo Speciality OMR", "lat": 12.9066, "lng": 80.2299,
     "specialties": ["cardiac", "accident", "pregnancy"],
     "has_ct": True, "has_trauma": False, "icu_free": 2, "beds_free": 9, "minutes_old": 6},
    {"id": 3, "name": "MIOT International", "lat": 13.0226, "lng": 80.1851,
     "specialties": ["cardiac", "stroke", "accident"],
     "has_ct": True, "has_trauma": True, "icu_free": 0, "beds_free": 12, "minutes_old": 4},
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


class RankRequest(BaseModel):
    lat: float
    lng: float
    type: str


def distance_km(lat1, lng1, lat2, lng2):
    r = math.radians
    a = (math.sin(r(lat2 - lat1) / 2) ** 2
         + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lng2 - lng1) / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/rank")
def rank(req: RankRequest):
    w = WEIGHTS.get(req.type, WEIGHTS["cardiac"])
    results = []
    for h in HOSPITALS:
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

ALERTS = []  # kept in memory for now; a database comes later


class AlertRequest(BaseModel):
    hospital_id: int
    type: str
    eta_min: int


@app.post("/alert")
def alert(req: AlertRequest):
    ALERTS.append({
        "hospital_id": req.hospital_id,
        "type": req.type,
        "eta_min": req.eta_min,
        "created_at": datetime.now().isoformat(),
    })
    return {"ok": True}


@app.get("/alerts/{hospital_id}")
def alerts_for_hospital(hospital_id: int):
    return [a for a in ALERTS if a["hospital_id"] == hospital_id]