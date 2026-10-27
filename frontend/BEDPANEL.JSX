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

export default function BedPanel() {
  const [open, setOpen] = useState(false);
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
      .limit(3);
    setAlerts(data || []);
  }

  useEffect(() => {
    if (!open) return;
    loadHospitals();
    const channel = supabase
      .channel("bedpanel")
      .on("postgres_changes", { event: "*", schema: "public", table: "hospitals" }, loadHospitals)
      .subscribe();
    return () => supabase.removeChannel(channel);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    loadAlerts();
    const timer = setInterval(loadAlerts, 3000);
    return () => clearInterval(timer);
  }, [open, selected]);

  const h = hospitals.find((x) => x.id === selected);

  async function save(changes) {
    setHospitals((list) => list.map((x) => (x.id === selected ? { ...x, ...changes } : x)));
    const { error } = await supabase.from("hospitals").update(changes).eq("id", selected);
    if (error) setError(error.message);
  }

  const btn = { width: 44, height: 44, fontSize: 22, borderRadius: 10, border: "1px solid #ccc", background: "#fff" };
  const box = { background: "#fff", border: "1px solid #dbe1ee", borderRadius: 12, padding: 12, marginTop: 14, color: "#1b2a4a" };

  return (
    <div style={box}>
      <button
        onClick={() => setOpen(!open)}
        style={{ width: "100%", padding: 10, borderRadius: 10, border: "none", background: "#263b6b", color: "#fff", fontWeight: 700 }}
      >
        {open ? "Hide hospital staff panel" : "🏥 Hospital staff: update beds"}
      </button>

      {open && (
        <div>
          {error && <p style={{ color: "crimson" }}>Error: {error}</p>}

          <select
            value={selected ?? ""}
            onChange={(e) => setSelected(Number(e.target.value))}
            style={{ width: "100%", padding: 10, fontSize: 16, marginTop: 10 }}
          >
            {hospitals.map((x) => (
              <option key={x.id} value={x.id}>{x.name}</option>
            ))}
          </select>

          {h && (
            <div>
              {FIELDS.map(([field, label]) => (
                <div key={field} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
                  <b>{label}</b>
                  <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                    <button style={btn} onClick={() => save({ [field]: Math.max(0, h[field] - 1) })}>−</button>
                    <b style={{ minWidth: 28, textAlign: "center", fontSize: 20 }}>{h[field]}</b>
                    <button style={btn} onClick={() => save({ [field]: h[field] + 1 })}>+</button>
                  </div>
                </div>
              ))}

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
                <b>Oxygen available</b>
                <button style={{ ...btn, width: 90, fontSize: 16 }} onClick={() => save({ oxygen: !h.oxygen })}>
                  {h.oxygen ? "Yes" : "No"}
                </button>
              </div>

              <h4 style={{ marginBottom: 4 }}>Incoming arrival alerts</h4>
              {alerts.length === 0 && <p style={{ color: "#666", margin: 0 }}>None yet.</p>}
              {alerts.map((a) => (
                <p key={a.id} style={{ margin: "4px 0" }}>
                  🚨 <b>{a.emergency_type}</b> patient arriving in {a.eta_min} min ({new Date(a.created_at).toLocaleTimeString()})
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}