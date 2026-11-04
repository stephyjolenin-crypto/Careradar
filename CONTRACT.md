POST  /rank   {lat, lng, type, exclude?: [hospital ids]}
              -> [{hospital (now with phone), score, eta_min, eta_source, age_min, reasons[]}]
POST  /route  {origin:{lat,lng}, destination:{lat,lng}}
              -> {minutes, km, line:[[lat,lng],...], source}
POST  /alert  {hospital_id, type, eta_min, summary?} -> {ok, id, status}
GET   /alert/{id}  -> {id, hospital_id, emergency_type, eta_min, status, summary, created_at}
PATCH /alert/{id}  {status: "accepted" | "diverted"} -> {ok, id, status}
GET   /alerts/{hospital_id} -> latest 20 alerts for that hospital
POST  /triage {text, lang} -> {type, urgency, message}
GET   /health -> {ok, supabase, gemini}
Alerts table: new columns status and summary (already added).
