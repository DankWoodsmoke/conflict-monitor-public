import { hasMultipleReports } from "../utils/verification";
import { apiFetch } from "../lib/api";
import { API_BASE } from "../lib/runtime";
import { useEffect, useState } from "react";



interface AccuracyStats {
  firmsSnapped: number;
  multiSource: number;
  singleSource: number;
  total: number;
}

export function AccuracyLayer() {
  const [stats, setStats] = useState<AccuracyStats | null>(null);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const fetchStats = () => {
      apiFetch(`${API_BASE}/events?limit=500`)
        .then(r => r.json())
        .then((events: any[]) => {
          const firmsSnapped = events.filter((e: any) =>
            (e.confirmed_networks || "").includes("SATELLITE")).length;
          const multiSource = events.filter((e: any) =>
            hasMultipleReports(e) && !(e.confirmed_networks || "").includes("SATELLITE")).length;
          const singleSource = events.length - firmsSnapped - multiSource;
          setStats({ firmsSnapped, multiSource, singleSource, total: events.length });
        })
        .catch(() => {});
    };
    fetchStats();
    const t = setInterval(fetchStats, 60000);
    return () => clearInterval(t);
  }, []);

  if (!stats || !visible) return (
    <button
      onClick={() => setVisible(true)}
      style={{
        position: "fixed", bottom: 24, left: 16, zIndex: 800,
        background: "#030d18", border: "1px solid #1a3a5a",
        color: "#3a6a8a", fontSize: 11, padding: "3px 8px",
        fontFamily: "monospace", cursor: "pointer", borderRadius: 3,
      }}
    >COVERAGE</button>
  );

  const firmsP = Math.round(stats.firmsSnapped / (stats.total || 1) * 100);
  const multiP = Math.round(stats.multiSource / (stats.total || 1) * 100);
  const singleP = 100 - firmsP - multiP;

  return (
    <div style={{
      position: "fixed", bottom: 24, left: 16, zIndex: 800,
      background: "rgba(3, 13, 24, 0.92)", border: "1px solid #1a3a5a",
      borderRadius: 4, padding: "8px 12px", minWidth: 180,
      fontFamily: "monospace", backdropFilter: "blur(8px)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontSize: 11, color: "#3a6a8a", letterSpacing: 1.5 }}>EVIDENCE COVERAGE</span>
        <button onClick={() => setVisible(false)} style={{ background: "none", border: "none", color: "#8b9eaf", cursor: "pointer", fontSize: 11, padding: 0 }}>×</button>
      </div>

      {/* Stacked bar */}
      <div style={{ height: 6, background: "#0a1a2a", borderRadius: 3, overflow: "hidden", display: "flex", marginBottom: 8 }}>
        <div style={{ width: `${firmsP}%`, background: "#0d6efd", transition: "width 0.5s" }} />
        <div style={{ width: `${multiP}%`, background: "#3fb950", transition: "width 0.5s" }} />
        <div style={{ width: `${singleP}%`, background: "#d29922", transition: "width 0.5s" }} />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11 }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span><span style={{ color: "#0d6efd" }}>■</span> SENSOR TAG</span>
          <span style={{ color: "#0d6efd", fontWeight: 700 }}>{stats.firmsSnapped} ({firmsP}%)</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span><span style={{ color: "#3fb950" }}>■</span> MULTI-SRC</span>
          <span style={{ color: "#3fb950", fontWeight: 700 }}>{stats.multiSource} ({multiP}%)</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span><span style={{ color: "#d29922" }}>■</span> SINGLE-SRC</span>
          <span style={{ color: "#d29922", fontWeight: 700 }}>{stats.singleSource} ({singleP}%)</span>
        </div>
        <div style={{ borderTop: "1px solid #1a2a3a", marginTop: 3, paddingTop: 3, display: "flex", justifyContent: "space-between", color: "#96a8b8" }}>
          <span>TOTAL EVENTS</span>
          <span style={{ color: "#58a6ff" }}>{stats.total}</span>
        </div>
      </div>
    </div>
  );
}
