import { nowMs } from "../lib/clock";
import { safeUrl } from "../lib/runtime";
import { apiFetch } from "../lib/api";
import { API_BASE } from "../lib/runtime";
import { useEffect, useMemo, useState } from "react";
import type { ConflictEvent } from "../types/event";
import { hasMultipleReports, isViralAmplification, getNetworks, NETWORK_META } from "../utils/verification";



function scoreColor(score: number): string {
  if (score >= 9) return "#ff2020";
  if (score >= 7) return "#ff4040";
  if (score >= 5) return "#f59e0b";
  return "#d29922";
}

function scoreLabel(score: number): string {
  if (score >= 9) return "CRITICAL";
  if (score >= 7) return "MAJOR";
  if (score >= 5) return "SIGNIFICANT";
  return "NOTABLE";
}

function timeAgo(ts: string): string {
  const diff = nowMs() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

interface AlertPanelProps {
  events: ConflictEvent[];
  onEventClick?: (evt: ConflictEvent) => void;
}

export function AlertPanel({ events, onEventClick }: AlertPanelProps) {
  const [dbAnomalies, setDbAnomalies] = useState<ConflictEvent[]>([]);

  useEffect(() => {
    apiFetch(`${API_BASE}/events/anomalies?limit=20&min_score=7`)
      .then((r) => r.ok ? r.json() : [])
      .then((data: ConflictEvent[]) => setDbAnomalies(data))
      .catch(() => {});
  }, []);

  const anomalies = useMemo(() => {
    const byId = new Map<number, ConflictEvent>();
    for (const e of dbAnomalies) byId.set(e.id, e);
    for (const e of events) {
      if (e.anomaly_score && e.anomaly_score >= 7) byId.set(e.id, e);
    }
    return Array.from(byId.values())
      .sort((a, b) =>
        (b.anomaly_score ?? 0) - (a.anomaly_score ?? 0) ||
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      )
      .slice(0, 15);
  }, [events, dbAnomalies]);

  if (anomalies.length === 0) return null;

  return (
    <div style={{
      background: "rgba(255,64,64,0.04)",
      border: "1px solid rgba(255,64,64,0.15)",
      borderRadius: 4,
      padding: "8px 12px",
      marginBottom: 8,
      maxHeight: 220,
      overflowY: "auto",
    }}>
      <div style={{
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: 2,
        color: "#ff4040",
        marginBottom: 6,
        fontFamily: "var(--font-mono)",
      }}>
        HIGH-SEVERITY EVENTS ({anomalies.length})
      </div>
      {anomalies.map((evt) => {
        const col = scoreColor(evt.anomaly_score ?? 0);
        const label = scoreLabel(evt.anomaly_score ?? 0);
        const hasMapPin = !!(evt.lat && evt.lon && evt.lat !== -25);
        const hasSourceUrl = !!(evt.source_url && evt.source_url.startsWith("http"));
        const srcLabel = evt.source_url?.includes("t.me")
          ? "↗ TG"
          : evt.source_url?.includes("x.com") || evt.source_url?.includes("xcancel") || evt.source_url?.includes("twitter")
          ? "↗ X"
          : "↗ SOURCE";

        return (
          <div
            key={evt.id}
            style={{
              padding: "6px 8px",
              marginBottom: 4,
              borderRadius: 3,
              background: "rgba(10,14,20,0.6)",
              border: `1px solid ${col}33`,
              transition: "border-color 0.15s",
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = `${col}66`; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = `${col}33`; }}
          >
            {/* Top row: severity badge + time + location */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
              <span style={{
                fontSize: 11, padding: "1px 5px", borderRadius: 2, fontWeight: 700,
                letterSpacing: 0.5, background: `${col}22`, color: col,
                border: `1px solid ${col}44`, fontFamily: "var(--font-mono)",
              }}>
                {label} {evt.anomaly_score}/10
              </span>
              <span style={{ fontSize: 11, color: "#5a6a7e", fontFamily: "var(--font-mono)" }}>
                {timeAgo(evt.timestamp)}
              </span>
              {evt.location_name && evt.location_name.toLowerCase() !== "unknown" && (
                <span style={{ fontSize: 11, color: "#58a6ff", fontFamily: "var(--font-mono)" }}>
                  📍 {evt.location_name}
                </span>
              )}
            </div>

            {/* Summary — factual, from source */}
            <div style={{
              fontSize: 12, color: "#c8d6e5", lineHeight: 1.4,
              fontFamily: "var(--font-mono)", marginBottom: 4,
            }}>
              {evt.summary}
            </div>

            {/* Confirmation status */}
            {hasMultipleReports(evt) && (() => {
              const nets = getNetworks(evt);
              return (
                <div
                  title={"Source groups: " + nets.map(n => NETWORK_META[n]?.tip ?? n).join(" + ")}
                  style={{
                    fontSize: 11, padding: "2px 7px", borderRadius: 2, marginBottom: 4,
                    background: "rgba(63,185,80,0.12)", color: "var(--accent-green)",
                    fontFamily: "var(--font-mono)", fontWeight: 700, letterSpacing: 1,
                    border: "1px solid rgba(63,185,80,0.35)",
                    display: "inline-flex", alignItems: "center", gap: 4, cursor: "help",
                  }}
                >
                  ↗ MULTIPLE REPORTS · {nets.map(n => NETWORK_META[n]?.short ?? n).join(" + ")}
                </div>
              );
            })()}
            {!hasMultipleReports(evt) && isViralAmplification(evt) && (
              <div
                title="4+ reports from the same information network. Origin independence remains unassessed."
                style={{
                  fontSize: 11, padding: "2px 7px", borderRadius: 2, marginBottom: 4,
                  background: "rgba(210,153,34,0.1)", color: "var(--accent-yellow)",
                  fontFamily: "var(--font-mono)", fontWeight: 700, letterSpacing: 1,
                  border: "1px solid rgba(210,153,34,0.3)",
                  display: "inline-flex", alignItems: "center", gap: 4, cursor: "help",
                }}
              >
                ⚡ AMPLIFIED — single-network viral
              </div>
            )}
            {/* Action row: map + source link — NO AI analysis text */}
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
              {hasMapPin && onEventClick && (
                <button
                  onClick={() => onEventClick(evt)}
                  style={{
                    background: "rgba(88,166,255,0.1)", border: "1px solid rgba(88,166,255,0.3)",
                    color: "#58a6ff", borderRadius: 3, padding: "2px 7px",
                    fontSize: 11, cursor: "pointer", fontFamily: "var(--font-mono)",
                    letterSpacing: 0.5,
                  }}
                >
                  🗺 Show on map
                </button>
              )}
              {hasSourceUrl && (
                <a
                  href={safeUrl(evt.source_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    background: "rgba(63,185,80,0.1)", border: "1px solid rgba(63,185,80,0.3)",
                    color: "#3fb950", borderRadius: 3, padding: "2px 7px",
                    fontSize: 11, textDecoration: "none", fontFamily: "var(--font-mono)",
                    letterSpacing: 0.5,
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(63,185,80,0.2)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(63,185,80,0.1)")}
                >
                  {srcLabel}
                </a>
              )}
              {!hasSourceUrl && (
                <span style={{
                  fontSize: 11, color: "#96a8b8", fontFamily: "var(--font-mono)", fontStyle: "italic",
                }}>
                  no source link
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
