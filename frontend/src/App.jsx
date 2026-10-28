import { useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import BedPanel from "./BedPanel.jsx";

const API = import.meta.env.VITE_API_URL;
const FALLBACK = { lat: 12.8728, lng: 80.2257 };
const TYPES = [
  ["cardiac", "❤️", "Cardiac", "Chest pain, heart attack"],
  ["stroke", "🧠", "Stroke", "Face drooping, slurred speech"],
  ["accident", "🚑", "Accident", "Injury, bleeding, trauma"],
  ["pregnancy", "🤰", "Pregnancy", "Labour, delivery, complications"],
];

function Recenter({ pos }) {
  const map = useMap();
  useEffect(() => {
    map.flyTo([pos.lat, pos.lng], 11, { duration: 1.2 });
  }, [pos.lat, pos.lng]);
  return null;
}

function ago(min) {
  if (min < 60) return `${min}m`;
  if (min < 1440) return `${Math.round(min / 60)}h`;
  return `${Math.round(min / 1440)}d`;
}

function badge(age) {
  if (age <= 15) return ["Live", "live"];
  if (age <= 40) return ["Aging", "aging"];
  return ["Stale", "stale"];
}

function barColor(score) {
  if (score >= 60) return "#1f9d55";
  if (score >= 35) return "#f08a2c";
  return "#e5484d";
}

export default function App() {
  const [pos, setPos] = useState(FALLBACK);
  const [type, setType] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [triage, setTriage] = useState(null);
  const [alerted, setAlerted] = useState(null);
  const typeRef = useRef(null);
  const resultsRef = useRef(null);

  useEffect(() => {
    fetch(`${API}/health`).catch(() => {}); // wakes the free server early
    navigator.geolocation?.getCurrentPosition(
      (p) => setPos({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => {}
    );
  }, []);

  async function rank(t, silent = false) {
    setType(t);
    typeRef.current = t;
    if (!silent) {
      setLoading(true);
      setError("");
      setAlerted(null);
    }
    try {
      const r = await fetch(`${API}/rank`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat: pos.lat, lng: pos.lng, type: t }),
      });
      if (!r.ok) throw new Error("bad response");
      setResults(await r.json());
      if (!silent) {
        setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
      }
    } catch {
      if (!silent) setError("Could not reach the server. Please try again.");
    }
    if (!silent) setLoading(false);
  }

  // re-rank every 5 seconds so bed changes appear live
  useEffect(() => {
    const id = setInterval(() => {
      if (typeRef.current) rank(typeRef.current, true);
    }, 5000);
    return () => clearInterval(id);
  }, [pos]);

  async function askTriage() {
    if (!text.trim()) return;
    setLoading(true);
    setError("");
    try {
      const r = await fetch(`${API}/triage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang: "en" }),
      });
      const d = await r.json();
      setTriage(d);
      await rank(d.type);
    } catch {
      setError("Could not reach the server. Please try again.");
    }
    setLoading(false);
  }

  async function alertER(h, eta) {
    try {
      await fetch(`${API}/alert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hospital_id: h.id, type, eta_min: eta }),
      });
      setAlerted(h.id);
    } catch {
      setError("Could not send the alert.");
    }
    window.open(
      `https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lng}`,
      "_blank"
    );
  }

  return (
    <div className="app">
      <div className="header">
        <div className="radar"><i /></div>
        <div className="logo">Care<span>Radar</span></div>
        <div className="live-pill">● Live data</div>
      </div>

      <div className="hero">
        <h1>The right hospital, right now.</h1>
        <p>Live ICU, bed and ventilator availability, ranked for your emergency.</p>
        <a className="sos" href="tel:108">📞 Call 108 for an ambulance</a>
      </div>

      <div className="section-title">What is the emergency?</div>
      <div className="types">
        {TYPES.map(([k, emoji, label, hint], i) => (
          <button
            key={k}
            className={`type ${type === k ? "active" : ""}`}
            style={{ animationDelay: `${i * 70}ms` }}
            onClick={() => rank(k)}
          >
            <span className="emoji">{emoji}</span>
            <b>{label}</b>
            <small>{hint}</small>
          </button>
        ))}
      </div>

      <div className="card triage">
        <b>Not sure? Describe it in English, Tamil or Hindi</b>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="e.g. நெஞ்சு வலி / सीने में दर्द / chest pain"
        />
        <button className="btn" onClick={askTriage}>Find the right care</button>
        {triage && (
          <div className="triage-out">
            <span className="tag type-tag">{triage.type.toUpperCase()}</span>
            <span className={`tag ${triage.urgency}`}>{triage.urgency}</span>
            <div style={{ marginTop: 8 }}>{triage.message}</div>
          </div>
        )}
      </div>

      {loading && (
        <div className="status"><span className="spinner" />Finding the best hospital…</div>
      )}
      {error && <div className="status err">{error}</div>}

      <div className="map-wrap">
        <MapContainer center={[pos.lat, pos.lng]} zoom={11} style={{ height: "100%", width: "100%" }}>
          <Recenter pos={pos} />
         <TileLayer
            attribution="© OpenStreetMap contributors"
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <CircleMarker center={[pos.lat, pos.lng]} radius={8} pathOptions={{ color: "#2b7fff", fillOpacity: 1 }}>
            <Popup>You are here</Popup>
          </CircleMarker>
          {results.map((r, i) => (
            <CircleMarker
              key={r.hospital.id}
              center={[r.hospital.lat, r.hospital.lng]}
              radius={i === 0 ? 12 : 8}
              pathOptions={{ color: barColor(r.score), fillOpacity: 0.9 }}
            >
              <Popup>
                {i + 1}. {r.hospital.name}
                <br />
                Score {r.score}
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      <div ref={resultsRef} />
      {type && <div className="section-title">Best hospitals for {type}</div>}

      {loading && results.length === 0 && (
        <>
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
        </>
      )}

      {results.slice(0, 4).map((r, i) => {
        const [label, cls] = badge(r.age_min);
        const h = r.hospital;
        return (
          <div
            key={`${type}-${h.id}`}
            className={`card result ${i === 0 ? "best" : ""}`}
            style={{ animationDelay: `${i * 90}ms` }}
          >
            {i === 0 && <div className="best-flag">★ BEST MATCH</div>}
            <div className="r-top">
              <div className="rank-no">{i + 1}</div>
              <div className="r-name">{h.name}</div>
              <div className="r-score">{r.score}</div>
            </div>
            <div className="bar">
              <div style={{ width: `${Math.min(100, r.score)}%`, background: barColor(r.score) }} />
            </div>
            <div className="chips">
              <span className="chip">🕒 {r.eta_min} min</span>
              <span className="chip">ICU {h.icu_free}</span>
              <span className="chip">Beds {h.beds_free}</span>
              <span className={`chip ${cls}`}>{label} · {ago(r.age_min)}</span>
            </div>
            {i === 0 && (
              <button className={`btn ${alerted === h.id ? "done" : ""}`} onClick={() => alertER(h, r.eta_min)}>
                {alerted === h.id ? "✓ ER alerted · opening route…" : "🚨 Alert ER and navigate"}
              </button>
            )}
          </div>
        );
      })}

      <BedPanel />

      <div className="footer">
        Demo data: bed availability is simulated. AI triage is guidance only, not a diagnosis.
      </div>
    </div>
  );
}