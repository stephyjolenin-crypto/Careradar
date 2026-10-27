import { useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

const API = import.meta.env.VITE_API_URL;
const FALLBACK = { lat: 12.8728, lng: 80.2257 };
const TYPES = [
  ["cardiac", "❤️ Cardiac"],
  ["stroke", "🧠 Stroke"],
  ["accident", "🚑 Accident"],
  ["pregnancy", "🤰 Pregnancy"],
];

function Recenter({ pos }) {
  const map = useMap();
  useEffect(() => {
    map.setView([pos.lat, pos.lng], 11);
  }, [pos.lat, pos.lng]);
  return null;
}

function badge(age) {
  if (age <= 15) return ["Live", "#1f9d55"];
  if (age <= 40) return ["Aging", "#c98a00"];
  return ["Stale", "#d92d20"];
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

  const card = {
    background: "#fff",
    border: "1px solid #dbe1ee",
    borderRadius: 12,
    padding: 12,
    marginTop: 10,
    color: "#1b2a4a",
  };

  return (
    <div
      style={{
        maxWidth: 560,
        margin: "0 auto",
        padding: 12,
        fontFamily: "system-ui, sans-serif",
        background: "#f4f6fb",
        minHeight: "100vh",
      }}
    >
      <h2 style={{ margin: "4px 0", color: "#1b2a4a" }}>
        Care<span style={{ color: "#f08a2c" }}>Radar</span>
      </h2>
      <p style={{ margin: "0 0 8px", color: "#5b6785" }}>
        The right hospital, right now. Call 108 in an emergency.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
        {TYPES.map(([k, label]) => (
          <button
            key={k}
            onClick={() => rank(k)}
            style={{
              padding: 14,
              fontSize: 16,
              fontWeight: 700,
              borderRadius: 12,
              border: "none",
              background: type === k ? "#f08a2c" : "#263b6b",
              color: "#fff",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={card}>
        <b>Describe the problem (English, Tamil or Hindi)</b>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          style={{ width: "100%", marginTop: 6, padding: 8, fontSize: 15, boxSizing: "border-box" }}
          placeholder="e.g. நெஞ்சு வலி / सीने में दर्द / chest pain"
        />
        <button
          onClick={askTriage}
          style={{
            marginTop: 6,
            padding: 10,
            width: "100%",
            borderRadius: 10,
            border: "none",
            background: "#f08a2c",
            color: "#fff",
            fontWeight: 700,
          }}
        >
          Find the right care
        </button>
        {triage && (
          <p style={{ margin: "8px 0 0" }}>
            <b>{triage.type.toUpperCase()}</b> · {triage.urgency}
            <br />
            {triage.message}
          </p>
        )}
      </div>

      {loading && <p style={{ color: "#5b6785" }}>Finding the best hospital…</p>}
      {error && <p style={{ color: "#d92d20" }}>{error}</p>}

      <div style={{ height: 260, marginTop: 10, borderRadius: 12, overflow: "hidden" }}>
        <MapContainer center={[pos.lat, pos.lng]} zoom={11} style={{ height: "100%", width: "100%" }}>
          <Recenter pos={pos} />
          <TileLayer
            attribution="© OpenStreetMap contributors"
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <CircleMarker
            center={[pos.lat, pos.lng]}
            radius={8}
            pathOptions={{ color: "#2b7fff", fillOpacity: 1 }}
          >
            <Popup>You are here</Popup>
          </CircleMarker>
          {results.map((r, i) => (
            <CircleMarker
              key={r.hospital.id}
              center={[r.hospital.lat, r.hospital.lng]}
              radius={i === 0 ? 12 : 8}
              pathOptions={{
                color: r.score < 30 ? "#d92d20" : i === 0 ? "#1f9d55" : "#f08a2c",
                fillOpacity: 0.9,
              }}
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

      {results.slice(0, 4).map((r, i) => {
        const [label, color] = badge(r.age_min);
        const h = r.hospital;
        return (
          <div key={h.id} style={card}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <b>
                {i + 1}. {h.name}
              </b>
              <b style={{ fontSize: 20, color: "#263b6b" }}>{r.score}</b>
            </div>
            <div style={{ color: "#5b6785", fontSize: 14 }}>
              {r.eta_min} min away ·{" "}
              <span
                style={{
                  background: color,
                  color: "#fff",
                  borderRadius: 99,
                  padding: "1px 8px",
                  fontSize: 12,
                }}
              >
                {label} {r.age_min}m
              </span>
            </div>
            <div style={{ margin: "6px 0" }}>
              ICU <b>{h.icu_free}</b> · Beds <b>{h.beds_free}</b>
            </div>
            {i === 0 && (
              <button
                onClick={() => alertER(h, r.eta_min)}
                style={{
                  width: "100%",
                  padding: 10,
                  borderRadius: 10,
                  border: "none",
                  background: "#f08a2c",
                  color: "#fff",
                  fontWeight: 700,
                }}
              >
                {alerted === h.id ? "ER alerted ✓ Opening route…" : "Alert ER and navigate"}
              </button>
            )}
          </div>
        );
      })}
      <p style={{ color: "#5b6785", fontSize: 12 }}>
        Demo data: bed availability is simulated. AI triage is guidance only.
      </p>
    </div>
  );
}