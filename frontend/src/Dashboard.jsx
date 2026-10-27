import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

const FIELDS = [
  ["icu_free", "ICU beds"],
  ["beds_free", "General beds"],
  ["ventilators_free", "Ventilators"],
];

export default function Dashboard() {
  const [hospitals, setHospitals] = useState([]);
  const [selected, setSelected] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState("");

  async function loadHospitals() {
    const { data, error } = await supabase.from("hospitals").select("*").order("name");
    if (error) return setError(error.message);
    setHospitals(data);
    setSelected((s) => s ?? data[0]?.id ?? null);
  }

  async function loadAlerts() {
    if (!selected) return;
    const { data } = await supabase
      .from("alerts")
      .select("*")
      .eq("hospital_id", selected)
      .order("created_at", { ascending: false })
      .limit(5);
    setAlerts(data || []);
  }

  useEffect(() => {
    loadHospitals();
    const channel = supabase
      .channel("dashboard")
      .on("postgres_changes", { event: "*", schema: "public", table: "hospitals" }, loadHospitals)
      .subscribe();
    return () => supabase.removeChannel(channel);
  }, []);

  useEffect(() => {
    loadAlerts();
    const timer = setInterval(loadAlerts, 3000);
    return () => clearInterval(timer);
  }, [selected]);

  const h = hospitals.find((x) => x.id === selected);

  async function save(changes) {
    setHospitals((list) => list.map((x) => (x.id === selected ? { ...x, ...changes } : x)));
    const { error } = await supabase.from("hospitals").update(changes).eq("id", selected);
    if (error) setError(error.message);
  }

  const minutesAgo = h ? Math.max(0, Math.round((Date.now() - new Date(h.updated_at)) / 60000)) : 0;
  const btn = { width: 44, height: 44, fontSize: 22, borderRadius: 10, border: "1px solid #ccc", background: "#fff" };

  return (
    <div style={{ maxWidth: 480, margin: "0 auto", padding: 16, fontFamily: "system-ui, sans-serif" }}>
      <h2>CareRadar Hospital Dashboard</h2>
      {error && <p style={{ color: "crimson" }}>Error: {error}</p>}

      <select
        value={selected ?? ""}
        onChange={(e) => setSelected(Number(e.target.value))}
        style={{ width: "100%", padding: 10, fontSize: 16 }}
      >
        {hospitals.map((x) => (
          <option key={x.id} value={x.id}>{x.name}</option>
        ))}
      </select>

      {h && (
        <div>
          {FIELDS.map(([field, label]) => (
            <div key={field} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16 }}>
              <b>{label}</b>
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <button style={btn} onClick={() => save({ [field]: Math.max(0, h[field] - 1) })}>−</button>
                <b style={{ minWidth: 28, textAlign: "center", fontSize: 20 }}>{h[field]}</b>
                <button style={btn} onClick={() => save({ [field]: h[field] + 1 })}>+</button>
              </div>
            </div>
          ))}

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16 }}>
            <b>Oxygen available</b>
            <button style={{ ...btn, width: 90, fontSize: 16 }} onClick={() => save({ oxygen: !h.oxygen })}>
              {h.oxygen ? "Yes" : "No"}
            </button>
          </div>

          <p style={{ color: "#666" }}>Last updated {minutesAgo} min ago</p>

          <h3>Incoming arrival alerts</h3>
          {alerts.length === 0 && <p style={{ color: "#666" }}>None yet.</p>}
          {alerts.map((a) => (
            <p key={a.id}>
              🚨 <b>{a.emergency_type}</b> patient arriving in {a.eta_min} min ({new Date(a.created_at).toLocaleTimeString()})
            </p>
          ))}
        </div>
      )}
    </div>
  );
}