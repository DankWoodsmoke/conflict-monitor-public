import { nowMs } from "../lib/clock";
import { safeUrl } from "../lib/runtime";
import { apiFetch } from "../lib/api";
import { API_BASE } from "../lib/runtime";
/**
 * IntelPulsePanel — floating collapsible intel dashboard
 *
 * Two modes:
 *   floating=false  →  sidebar embed (legacy, full-height)
 *   floating=true   →  map overlay at bottom-right, collapses to a stats strip
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { ConflictEvent } from "../types/event";
import {
  hasMultipleReports,
  isViralAmplification,
  getNetworks,
  NETWORK_META,
} from "../utils/verification";



// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(ts: string): string {
  const diff = nowMs() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

function sevColor(sev: number): string {
  if (sev >= 9) return "#ff2020";
  if (sev >= 7) return "#ff6030";
  if (sev >= 5) return "#f59e0b";
  return "#6b7280";
}

function sevLabel(sev: number): string {
  if(!Number.isFinite(sev)||sev<1)return "UNSCORED";
  if (sev >= 9) return "CRIT";
  if (sev >= 7) return "HIGH";
  if (sev >= 5) return "MOD";
  return "LOW";
}

// ── Stats data hook ───────────────────────────────────────────────────────────

function useStats(allEvents: ConflictEvent[]) {
  const now = nowMs();
  const oneHour = 60 * 60 * 1000;

  const eventsLastHr = useMemo(
    () => allEvents.filter((e) => now - new Date(e.timestamp).getTime() < oneHour).length,
    [allEvents]
  );
  const baseline24h = useMemo(() => {
    const inLast24 = allEvents.filter((e) => now - new Date(e.timestamp).getTime() < 24 * oneHour).length;
    return Math.max(1, Math.round(inLast24 / 24));
  }, [allEvents]);

  const { confirmed24h, total24h } = useMemo(() => {
    const recent = allEvents.filter((e) => now - new Date(e.timestamp).getTime() < 24 * oneHour);
    const conf = recent.filter((e) => hasMultipleReports(e)).length;
    return { confirmed24h: conf, total24h: recent.length };
  }, [allEvents]);
  const confRate = total24h > 0 ? Math.round((confirmed24h / total24h) * 100) : 0;

  const activeNets = useMemo(() => {
    const nets = new Set<string>();
    allEvents
      .filter((e) => now - new Date(e.timestamp).getTime() < 6 * oneHour)
      .forEach((e) => getNetworks(e).forEach((n) => nets.add(n)));
    return nets.size;
  }, [allEvents]);

  const highSevCount = useMemo(
    () =>
      allEvents.filter(
        (e) => (e.severity ?? 0) >= 7 && now - new Date(e.timestamp).getTime() < 24 * oneHour
      ).length,
    [allEvents]
  );

  const velocityDelta = eventsLastHr - baseline24h;
  const velColor = velocityDelta > 5 ? "#ff6030" : velocityDelta > 2 ? "#f59e0b" : "#3fb950";
  const confColor = confRate >= 10 ? "#3fb950" : confRate >= 5 ? "#f59e0b" : "#6b7280";
  const netColor = activeNets >= 3 ? "#3fb950" : activeNets >= 2 ? "#f59e0b" : "#6b7280";
  const sevCount_color = highSevCount >= 5 ? "#ff2020" : highSevCount >= 2 ? "#ff6030" : "#6b7280";

  return {
    eventsLastHr, baseline24h, velocityDelta, velColor,
    confRate, confColor,
    activeNets, netColor,
    highSevCount, sevCount_color,
  };
}

// ── Stat chip (for compact strip) ─────────────────────────────────────────────

function StatChip({
  value, label, color, title,
}: {
  value: string | number; label: string; color: string; title?: string;
}) {
  return (
    <div
      title={title}
      style={{
        display: "flex", flexDirection: "column", alignItems: "center",
        gap: 1, cursor: title ? "help" : "default",
        minWidth: 36,
      }}
    >
      <span style={{ fontSize: 12, fontWeight: 700, color, fontFamily: "var(--font-mono)", lineHeight: 1 }}>
        {value}
      </span>
      <span style={{
        fontSize: 11, color: "#96a8b8", fontFamily: "var(--font-mono)",
        letterSpacing: 0.4, textTransform: "uppercase",
      }}>
        {label}
      </span>
    </div>
  );
}

// ── Event row ─────────────────────────────────────────────────────────────────

interface EventRowProps {
  evt: ConflictEvent;
  onEventClick?: (evt: ConflictEvent) => void;
  variant: "confirmed" | "severe";
}

function EventRow({ evt, onEventClick, variant }: EventRowProps) {
  const nets = getNetworks(evt);
  const hasPin = !!(evt.lat && evt.lon && evt.lat !== -25);
  const hasSrc = !!(evt.source_url?.startsWith("http"));
  const srcLabel = evt.source_url?.includes("t.me")
    ? "TG"
    : evt.source_url?.includes("x.com") || evt.source_url?.includes("twitter")
    ? "X"
    : "SRC";
  const viral = isViralAmplification(evt);
  const borderColor =
    variant === "confirmed"
      ? "rgba(63,185,80,0.22)"
      : `${sevColor(evt.severity ?? 0)}2a`;

  return (
    <div
      style={{
        padding: "5px 8px", marginBottom: 3, borderRadius: 3,
        background: "rgba(10,14,20,0.65)",
        border: `1px solid ${borderColor}`,
        transition: "border-color 0.15s",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor =
          variant === "confirmed" ? "rgba(63,185,80,0.45)" : `${sevColor(evt.severity ?? 0)}55`;
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = borderColor;
      }}
    >
      {/* Row 1: badge + time + location */}
      <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 2, flexWrap: "wrap" }}>
        {variant === "confirmed" ? (
          <span
            title={"Source groups: " + nets.map((n) => NETWORK_META[n]?.tip ?? n).join(" + ")}
            style={{
              fontSize: 11, padding: "1px 5px", borderRadius: 2,
              background: "rgba(63,185,80,0.12)", color: "var(--accent-green)",
              border: "1px solid rgba(63,185,80,0.35)", fontFamily: "var(--font-mono)",
              fontWeight: 700, letterSpacing: 0.5, cursor: "help", whiteSpace: "nowrap",
            }}
          >
            ✓ {nets.map((n) => NETWORK_META[n]?.short ?? n).join("+")}
          </span>
        ) : (
          <span
            style={{
              fontSize: 11, padding: "1px 5px", borderRadius: 2,
              background: `${sevColor(evt.severity ?? 0)}1a`,
              color: sevColor(evt.severity ?? 0),
              border: `1px solid ${sevColor(evt.severity ?? 0)}44`,
              fontFamily: "var(--font-mono)", fontWeight: 700, letterSpacing: 0.5, whiteSpace: "nowrap",
            }}
          >
            {sevLabel(evt.severity ?? 0)} {evt.severity>0?evt.severity:""}
          </span>
        )}
        {viral && (
          <span
            title="4+ repeated reports; origin independence remains unassessed"
            style={{
              fontSize: 11, padding: "1px 4px", borderRadius: 2,
              background: "rgba(210,153,34,0.1)", color: "var(--accent-yellow, #d29922)",
              border: "1px solid rgba(210,153,34,0.3)",
              fontFamily: "var(--font-mono)", fontWeight: 700, cursor: "help", whiteSpace: "nowrap",
            }}
          >
            ⚡ AMP
          </span>
        )}
        <span style={{ fontSize: 11, color: "#96a8b8", fontFamily: "var(--font-mono)" }}>
          {timeAgo(evt.timestamp)}
        </span>
        {evt.location_name && evt.location_name.toLowerCase() !== "unknown" && (
          <span style={{
            fontSize: 11, color: "#58a6ff", fontFamily: "var(--font-mono)",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 110,
          }}>
            📍 {evt.location_name}
          </span>
        )}
      </div>

      {/* Summary */}
      <div
        style={{
          fontSize: 12, color: "#c8d6e5", lineHeight: 1.35, fontFamily: "var(--font-mono)",
          marginBottom: 4,
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}
      >
        {evt.summary}
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
        {hasPin && onEventClick && (
          <button
            onClick={() => onEventClick(evt)}
            style={{
              background: "rgba(88,166,255,0.1)", border: "1px solid rgba(88,166,255,0.3)",
              color: "#58a6ff", borderRadius: 3, padding: "1px 6px",
              fontSize: 11, cursor: "pointer", fontFamily: "var(--font-mono)",
            }}
          >
            🗺 map
          </button>
        )}
        {hasSrc && (
          <a
            href={safeUrl(evt.source_url)}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              background: "rgba(63,185,80,0.08)", border: "1px solid rgba(63,185,80,0.22)",
              color: "#3fb950", borderRadius: 3, padding: "1px 6px",
              fontSize: 11, textDecoration: "none", fontFamily: "var(--font-mono)",
            }}
          >
            ↗ {srcLabel}
          </a>
        )}
        {(evt.report_count ?? 1) > 1 && (
          <span style={{ fontSize: 11, color: "#96a8b8", fontFamily: "var(--font-mono)" }}>
            🔗 {evt.report_count}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface IntelPulsePanelProps {
  events: ConflictEvent[];
  allEvents: ConflictEvent[];
  onEventClick?: (evt: ConflictEvent) => void;
  /** When true: renders as a floating, collapsible map overlay */
  floating?: boolean;
}

export function IntelPulsePanel({
  events,
  allEvents,
  onEventClick,
  floating = false,
}: IntelPulsePanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [tab, setTab] = useState<"confirmed" | "severe">("confirmed");

  // Pulse animation
  const [pulse, setPulse] = useState(false);
  const prevCount = useRef(events.length);
  useEffect(() => {
    if (events.length !== prevCount.current) {
      setPulse(true);
      prevCount.current = events.length;
      const t = setTimeout(() => setPulse(false), 600);
      return () => clearTimeout(t);
    }
  }, [events.length]);

  const stats = useStats(allEvents);

  // Fetch DB events
  const [dbConfirmed, setDbConfirmed] = useState<ConflictEvent[]>([]);
  const [dbHighSev, setDbHighSev] = useState<ConflictEvent[]>([]);
  useEffect(() => {
    const load = () => {
      apiFetch(`${API_BASE}/events?limit=200&after=${new Date(nowMs() - 24 * 3600000).toISOString()}`)
        .then((r) => (r.ok ? r.json() : []))
        .then((data: ConflictEvent[]) => {
          setDbConfirmed(data.filter((e) => hasMultipleReports(e)));
          setDbHighSev(data.filter((e) => (e.severity ?? 0) >= 7 && !hasMultipleReports(e)));
        })
        .catch(() => {});
    };
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, []);

  const confirmedEvents = useMemo(() => {
    const byId = new Map<number, ConflictEvent>();
    for (const e of dbConfirmed) byId.set(e.id, e);
    for (const e of events) {
      if (hasMultipleReports(e)) byId.set(e.id, e);
    }
    return Array.from(byId.values())
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
      .slice(0, 10);
  }, [events, dbConfirmed]);

  const highSevEvents = useMemo(() => {
    const byId = new Map<number, ConflictEvent>();
    for (const e of dbHighSev) byId.set(e.id, e);
    for (const e of events) {
      if ((e.severity ?? 0) >= 7 && !hasMultipleReports(e)) byId.set(e.id, e);
    }
    return Array.from(byId.values())
      .sort(
        (a, b) =>
          (b.severity ?? 0) - (a.severity ?? 0) ||
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      )
      .slice(0, 8);
  }, [events, dbHighSev]);

  const tabBtn = (active: boolean, accent: string) =>
    ({
      flex: 1, padding: "4px 0", fontSize: 11, fontWeight: 700,
      fontFamily: "var(--font-mono)", letterSpacing: 0.8, cursor: "pointer",
      border: "none",
      borderBottom: active ? `2px solid ${accent}` : "2px solid transparent",
      background: "transparent",
      color: active ? accent : "#96a8b8",
      transition: "color 0.15s, border-color 0.15s",
    } as React.CSSProperties);

  // ── FLOATING mode ─────────────────────────────────────────────────────────
  if (floating) {
    return (
      <div
        style={{
          position: "absolute",
          top: 82,          // below Leaflet zoom controls (top-right)
          right: 10,
          zIndex: 1001,
          width: expanded ? 270 : "auto",
          fontFamily: "var(--font-mono)",
          pointerEvents: "auto",
          // Drop shadow for map readability
          filter: "drop-shadow(0 2px 8px rgba(0,0,0,0.7))",
        }}
      >
        {/* ── Collapsed stats bar (always visible) ── */}
        <button
          onClick={() => setExpanded((x) => !x)}
          style={{
            width: expanded ? "100%" : "auto",
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "5px 10px",
            background: "rgba(6,10,15,0.92)",
            border: "1px solid rgba(88,166,255,0.22)",
            borderRadius: expanded ? "4px 4px 0 0" : 4,
            cursor: "pointer",
            color: "#58a6ff",
            fontSize: 11,
            letterSpacing: 1.2,
            fontWeight: 700,
            fontFamily: "var(--font-mono)",
          }}
        >
          {/* Title + pulse dot */}
          <span style={{ display: "flex", alignItems: "center", gap: 5, color: "#7ab8d4", whiteSpace: "nowrap" }}>
            <span
              style={{
                width: 6, height: 6, borderRadius: "50%",
                background: pulse ? "#3fb950" : "#2d6e3e",
                boxShadow: pulse ? "0 0 5px #3fb950" : "none",
                transition: "background 0.3s, box-shadow 0.3s",
                display: "inline-block", flexShrink: 0,
              }}
            />
            MULTI-REPORT ITEMS
          </span>

          {/* Compact stats */}
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span title={`${stats.eventsLastHr} events/hr (24h avg ${stats.baseline24h}/hr)`}
              style={{ color: stats.velColor, fontSize: 12, fontWeight: 700 }}>
              {stats.eventsLastHr}
              <span style={{ fontSize: 11, color: "#96a8b8", marginLeft: 2 }}>/hr</span>
            </span>
            <span title={`${stats.confRate}% reported by multiple sources`}
              style={{ color: stats.confColor, fontSize: 12, fontWeight: 700 }}>
              {stats.confRate}%
              <span style={{ fontSize: 11, color: "#96a8b8", marginLeft: 2 }}>multi-source</span>
            </span>
            <span title={`${stats.highSevCount} high-severity events (24h)`}
              style={{ color: stats.sevCount_color, fontSize: 12, fontWeight: 700 }}>
              {stats.highSevCount}
              <span style={{ fontSize: 11, color: "#96a8b8", marginLeft: 2 }}>high</span>
            </span>
          </div>

          {/* Expand/collapse chevron */}
          <span style={{ color: "#96a8b8", fontSize: 11, marginLeft: "auto" }}>
            {expanded ? "▼" : "▲"}
          </span>
        </button>

        {/* ── Expanded body ── */}
        {expanded && (
          <div
            style={{
              background: "rgba(6,10,15,0.95)",
              border: "1px solid rgba(88,166,255,0.18)",
              borderTop: "none",
              borderRadius: "0 0 4px 4px",
              overflow: "hidden",
            }}
          >
            {/* Full stats strip */}
            <div
              style={{
                display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr",
                gap: 2, padding: "6px 10px",
                borderBottom: "1px solid rgba(255,255,255,0.04)",
              }}
            >
              <StatChip value={stats.eventsLastHr} label="EVT/HR" color={stats.velColor}
                title={`${stats.eventsLastHr} events in past hour (24h avg: ${stats.baseline24h}/hr)`} />
              <StatChip value={`${stats.confRate}%`} label="MULTI-SOURCE" color={stats.confColor}
                title="Share of reports with multiple source records; not a probability of truth" />
              <StatChip value={stats.activeNets} label="NETS" color={stats.netColor}
                title="Distinct information networks active in past 6h" />
              <StatChip value={stats.highSevCount} label="HIGH SEV" color={stats.sevCount_color}
                title="Severity ≥ 7 events in past 24h" />
            </div>

            {/* Tab bar */}
            <div style={{ display: "flex", padding: "0 4px", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
              <button style={tabBtn(tab === "confirmed", "#3fb950")} onClick={() => setTab("confirmed")}>
                ↗ MULTIPLE REPORTS ({confirmedEvents.length})
              </button>
              <button style={tabBtn(tab === "severe", "#ff6030")} onClick={() => setTab("severe")}>
                ⚠ HIGH SEV ({highSevEvents.length})
              </button>
            </div>

            {/* Events */}
            <div style={{ maxHeight: 240, overflowY: "auto", padding: "5px 7px 4px" }}>
              {tab === "confirmed" && (
                <>
                  {confirmedEvents.length === 0 ? (
                    <div style={{
                      padding: "14px 8px", textAlign: "center",
                      fontSize: 11, color: "#96a8b8", lineHeight: 1.5,
                    }}>
                      No reported by multiple sources events yet.
                      <br />
                      <span style={{ fontSize: 11, color: "#8b9eaf" }}>
                        Multiple publishers may share one origin; networks
                        <br />report the same event.
                      </span>
                    </div>
                  ) : (
                    confirmedEvents.map((evt) => (
                      <EventRow key={evt.id} evt={evt} onEventClick={onEventClick} variant="confirmed" />
                    ))
                  )}
                </>
              )}
              {tab === "severe" && (
                <>
                  {highSevEvents.length === 0 ? (
                    <div style={{ padding: "14px 8px", textAlign: "center", fontSize: 11, color: "#96a8b8" }}>
                      No single-source high-severity reports.
                    </div>
                  ) : (
                    <>
                      <div style={{ fontSize: 11, color: "#96a8b8", marginBottom: 4, fontStyle: "italic" }}>
                        Severity ≥ 7, not yet reported by multiple sources
                      </div>
                      {highSevEvents.map((evt) => (
                        <EventRow key={evt.id} evt={evt} onEventClick={onEventClick} variant="severe" />
                      ))}
                    </>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── SIDEBAR mode (non-floating) ───────────────────────────────────────────
  return (
    <div style={{
      background: "rgba(13,17,23,0.85)",
      border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: 4, marginBottom: 8, overflow: "hidden", flexShrink: 0,
    }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "5px 10px 4px", borderBottom: "1px solid rgba(255,255,255,0.05)",
      }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 2, color: "#58a6ff", fontFamily: "var(--font-mono)", textTransform: "uppercase" }}>
          Verified Reports
        </span>
        <span style={{
          width: 7, height: 7, borderRadius: "50%",
          background: pulse ? "#3fb950" : "#2d6e3e",
          boxShadow: pulse ? "0 0 6px #3fb950" : "none",
          transition: "background 0.3s, box-shadow 0.3s", display: "inline-block",
        }} />
      </div>

      {/* Stats */}
      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 4,
        padding: "6px 10px", background: "rgba(10,14,20,0.6)",
        borderBottom: "1px solid rgba(255,255,255,0.05)", marginBottom: 6,
      }}>
        <StatChip value={stats.eventsLastHr} label="EVT/HR" color={stats.velColor} />
        <StatChip value={`${stats.confRate}%`} label="MULTI-SOURCE" color={stats.confColor} />
        <StatChip value={stats.activeNets} label="NETS" color={stats.netColor} />
        <StatChip value={stats.highSevCount} label="HIGH SEV" color={stats.sevCount_color} />
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid rgba(255,255,255,0.05)", padding: "0 4px" }}>
        <button style={tabBtn(tab === "confirmed", "#3fb950")} onClick={() => setTab("confirmed")}>
          ↗ MULTIPLE REPORTS ({confirmedEvents.length})
        </button>
        <button style={tabBtn(tab === "severe", "#ff6030")} onClick={() => setTab("severe")}>
          ⚠ HIGH SEV ({highSevEvents.length})
        </button>
      </div>

      {/* Events */}
      <div style={{ maxHeight: 260, overflowY: "auto", padding: "6px 8px 4px" }}>
        {tab === "confirmed" && confirmedEvents.length === 0 && (
          <div style={{ padding: "16px 8px", textAlign: "center", fontSize: 11, color: "#96a8b8", lineHeight: 1.5, fontFamily: "var(--font-mono)" }}>
            No reported by multiple sources events yet.
          </div>
        )}
        {tab === "confirmed" && confirmedEvents.map((evt) => (
          <EventRow key={evt.id} evt={evt} onEventClick={onEventClick} variant="confirmed" />
        ))}
        {tab === "severe" && highSevEvents.length === 0 && (
          <div style={{ padding: "16px 8px", textAlign: "center", fontSize: 11, color: "#96a8b8", fontFamily: "var(--font-mono)" }}>
            No single-source high-severity reports.
          </div>
        )}
        {tab === "severe" && highSevEvents.length > 0 && (
          <>
            <div style={{ fontSize: 11, color: "#96a8b8", marginBottom: 5, fontStyle: "italic", fontFamily: "var(--font-mono)" }}>
              Severity ≥ 7, not yet reported by multiple sources — treat with caution
            </div>
            {highSevEvents.map((evt) => (
              <EventRow key={evt.id} evt={evt} onEventClick={onEventClick} variant="severe" />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
