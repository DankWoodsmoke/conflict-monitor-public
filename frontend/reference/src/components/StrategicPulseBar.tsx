import { nowMs } from "../lib/clock";
import { safeUrl } from "../lib/runtime";
import { apiFetch } from "../lib/api";
import { API_BASE } from "../lib/runtime";
/**
 * StrategicPulseBar — horizontal intelligence summary strip + SITREP system
 *
 * Features:
 *   - Live escalation level badge + headline teaser
 *   - Chokepoint status (Hormuz, Bab-el-Mandeb, Suez)
 *   - Verification stats + event rate
 *   - Full SITREP modal with:
 *       • Source events panel (key events with links to originals)
 *       • Escalation history strip (last 5 SITREPs)
 *       • All analysis sections
 *       • Archive button
 *   - SITREP Archive modal (browse all past reports)
 */
import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import type { ConflictEvent } from "../types/event";
import { hasMultipleReports } from "../utils/verification";



// ── Types ─────────────────────────────────────────────────────────────────────
interface Sitrep {
  id: number;
  generated_at: string;
  trigger: string;
  events_analyzed: number;
  headline: string;
  situation: string;
  escalation_text: string;
  escalation_level: "STABLE" | "ELEVATED" | "ESCALATING" | "CRITICAL";
  economic_exposure: string;
  game_theory: string;
  humanitarian_ground: string;
  historical_analogue: string;
  key_event_ids: number[];
}

interface SitrepSummary {
  id: number;
  generated_at: string;
  trigger: string;
  events_analyzed: number;
  headline: string;
  escalation_level: "STABLE" | "ELEVATED" | "ESCALATING" | "CRITICAL";
  key_event_ids: number[];
}

interface SourceEvent {
  id: number;
  source: string;
  channel_name: string;
  network: string;
  summary: string;
  source_url: string;
  severity: number;
  event_type: string;
  location_name: string;
  timestamp: string;
  reporting_channels: string;
  confirmed_networks: string;
  source_reliability: number | null;
}

// ── Escalation colors ─────────────────────────────────────────────────────────
const ESCALATION_COLOR: Record<string, string> = {
  STABLE:     "#3fb950",
  ELEVATED:   "#d29922",
  ESCALATING: "#f0883e",
  CRITICAL:   "#f85149",
};
const ESCALATION_BG: Record<string, string> = {
  STABLE:     "rgba(63,185,80,0.08)",
  ELEVATED:   "rgba(210,153,34,0.08)",
  ESCALATING: "rgba(240,136,62,0.08)",
  CRITICAL:   "rgba(248,81,73,0.08)",
};

// ── Chokepoint detection ──────────────────────────────────────────────────────
const CHOKEPOINTS = [
  { id: "hormuz",  label: "HORMUZ",        keywords: ["hormuz", "strait of hormuz", "persian gulf"] },
  { id: "bab",     label: "BAB-EL-MANDEB", keywords: ["bab el-mandeb","bab-el-mandeb","red sea","houthi","aden"] },
  { id: "suez",    label: "SUEZ",          keywords: ["suez","suez canal","ismailia","port said"] },
];
type ChokepointStatus = "clear" | "elevated" | "active";
const CP_COLOR: Record<ChokepointStatus, string> = { clear:"#3fb950", elevated:"#d29922", active:"#f85149" };

function getChokepointStatus(events: ConflictEvent[], cp: typeof CHOKEPOINTS[0]): ChokepointStatus {
  const cutoff = nowMs() - 6 * 3600000;
  const rel = events.filter(e => {
    if (new Date(e.timestamp).getTime() < cutoff) return false;
    const txt = `${(e.location_name??"").toLowerCase()} ${(e.summary??"").toLowerCase()}`;
    return cp.keywords.some(k => txt.includes(k));
  });
  if (rel.some(e => e.severity >= 7)) return "active";
  if (rel.length > 0) return "elevated";
  return "clear";
}

// ── Source network badge color ────────────────────────────────────────────────
const NETWORK_COLOR: Record<string, string> = {
  X:   "#1d9bf0",
  TG:  "#229ED9",
  RSS: "#ff6b35",
};
function netColor(net: string): string {
  return NETWORK_COLOR[net] ?? "#58a6ff";
}

// ── Severity bar ──────────────────────────────────────────────────────────────
function SevBar({ sev }: { sev: number }) {
  const col = sev >= 8 ? "#f85149" : sev >= 6 ? "#f0883e" : sev >= 4 ? "#d29922" : "#3fb950";
  return (
    <div style={{ display:"flex", alignItems:"center", gap:2 }}>
      {[...Array(5)].map((_,i) => (
        <div key={i} style={{
          width:3, height: 4 + i*2, borderRadius:1,
          background: i < Math.ceil(sev/2) ? col : "rgba(255,255,255,0.1)",
        }} />
      ))}
    </div>
  );
}

// ── Relative time ─────────────────────────────────────────────────────────────
function relTime(iso: string): string {
  const diff = (nowMs() - new Date(iso).getTime()) / 60000;
  if (diff < 60) return `${Math.round(diff)}m ago`;
  if (diff < 1440) return `${Math.round(diff/60)}h ago`;
  return `${Math.round(diff/1440)}d ago`;
}

// ── Parse src citations from bullet text ──────────────────────────────────────
function parseSrcIds(text: string): number[] {
  const ids: number[] = [];
  const re = /\[src:([\d,]+)\]/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    m[1].split(",").map(Number).filter(Boolean).forEach(id => ids.push(id));
  }
  return [...new Set(ids)]; // dedupe
}
function stripSrcCitation(text: string): string {
  return text.replace(/\s*\[src:[\d,]+\]/g, "").trim();
}

// ── Source Events Panel ───────────────────────────────────────────────────────
function SourceEventsPanel({
  events, loading, highlightId, accentColor,
}: {
  events: SourceEvent[];
  loading: boolean;
  highlightId: number | null;
  accentColor: string;
}) {

  return (
    <div style={{
      borderLeft: `3px solid ${accentColor}45`,
      background: `${accentColor}04`,
      borderBottom: "1px solid rgba(255,255,255,0.05)",
    }}>
      {/* Header */}
      <div style={{
        display:"flex", alignItems:"center", justifyContent:"space-between",
        padding:"9px 16px 6px",
        borderBottom:"1px solid rgba(255,255,255,0.04)",
      }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <span style={{ fontSize:12, color:accentColor, fontWeight:800, textShadow:`0 0 8px ${accentColor}55` }}>⟢</span>
          <div>
            <div style={{ fontSize:11, fontWeight:800, letterSpacing:1.8, color:accentColor, textTransform:"uppercase" }}>
              SOURCE INTELLIGENCE
            </div>
            <div style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.55, letterSpacing:0.4, marginTop:1 }}>
              {loading ? "fetching..." : `${events.length} key events that drove this analysis — click any to view original source`}
            </div>
          </div>
        </div>
        <div style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.4, letterSpacing:0.8 }}>
          SOURCES
        </div>
      </div>

      {/* Event list */}
      <div style={{ maxHeight:220, overflowY:"auto" }}>
        {loading && (
          <div style={{ padding:"16px", fontSize:11, color:"var(--text-secondary)", opacity:0.5, textAlign:"center" }}>
            Loading source events…
          </div>
        )}
        {!loading && events.length === 0 && (
          <div style={{ padding:"16px", fontSize:11, color:"var(--text-secondary)", opacity:0.5, textAlign:"center" }}>
            No source events found for this SITREP
          </div>
        )}
        {events.map((e, i) => (
          <div key={e.id} id={`src-evt-${e.id}`} style={{
            display:"flex", alignItems:"flex-start", gap:10,
            padding:"7px 16px",
            borderBottom: i < events.length-1 ? "1px solid rgba(255,255,255,0.03)" : "none",
            transition:"background 0.3s",
            background: highlightId === e.id ? "rgba(88,166,255,0.12)" : "transparent",
            boxShadow: highlightId === e.id ? "inset 3px 0 0 #58a6ff" : "none",
          }}
            onMouseEnter={el => { if (highlightId !== e.id) el.currentTarget.style.background = "rgba(255,255,255,0.025)"; }}
            onMouseLeave={el => { if (highlightId !== e.id) el.currentTarget.style.background = "transparent"; }}
          >
            {/* Network badge + severity */}
            <div style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:4, flexShrink:0, paddingTop:1 }}>
              <div style={{
                fontSize:11, fontWeight:800, padding:"2px 5px", borderRadius:3,
                background:`${netColor(e.network)}18`,
                color:netColor(e.network),
                border:`1px solid ${netColor(e.network)}44`,
                letterSpacing:0.5,
              }}>{e.network}</div>
              <SevBar sev={e.severity} />
            </div>

            {/* Content */}
            <div style={{ flex:1, minWidth:0 }}>
              <div style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.6, marginBottom:2, letterSpacing:0.3 }}>
                {e.channel_name || e.source}
                {e.location_name && ` · ${e.location_name}`}
                {" · "}{relTime(e.timestamp)}
                {e.confirmed_networks && e.confirmed_networks.includes(",") && (
                  <span style={{ color:"#3fb950", marginLeft:4 }}>↗ MULTIPLE REPORTS</span>
                )}
              </div>
              <div style={{ fontSize:12, lineHeight:1.5, color:"var(--text-primary)", opacity:0.88, fontFamily:"var(--font-sans)" }}>
                {e.summary.slice(0, 200)}{e.summary.length > 200 ? "…" : ""}
              </div>
            </div>

            {/* Open link */}
            {e.source_url && (
              <a
                href={safeUrl(e.source_url)}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  flexShrink:0,
                  fontSize:11, color:netColor(e.network), textDecoration:"none",
                  padding:"4px 8px", borderRadius:3,
                  border:`1px solid ${netColor(e.network)}33`,
                  background:`${netColor(e.network)}0d`,
                  display:"flex", alignItems:"center", gap:3,
                  transition:"all 0.15s",
                  marginTop:1,
                  letterSpacing:0.5,
                  fontFamily:"var(--font-mono)",
                }}
                onMouseEnter={el => {
                  (el.currentTarget as HTMLElement).style.background = `${netColor(e.network)}22`;
                  (el.currentTarget as HTMLElement).style.borderColor = `${netColor(e.network)}66`;
                }}
                onMouseLeave={el => {
                  (el.currentTarget as HTMLElement).style.background = `${netColor(e.network)}0d`;
                  (el.currentTarget as HTMLElement).style.borderColor = `${netColor(e.network)}33`;
                }}
              >
                VIEW ↗
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Escalation History Strip ──────────────────────────────────────────────────
function EscalationHistoryStrip({
  currentId, accentColor, onNavigate,
}: {
  currentId: number;
  accentColor: string;
  onNavigate?: (s: Sitrep) => void;
}) {
  const [history, setHistory]   = useState<SitrepSummary[]>([]);
  const [hoverId, setHoverId]   = useState<number | null>(null);
  const [loading, setLoading]   = useState<number | null>(null); // id being fetched

  useEffect(() => {
    apiFetch(`${API_BASE}/sitreps/?limit=10`)
      .then(r => r.ok ? r.json() : [])
      .then(d => setHistory(Array.isArray(d) ? d.slice().reverse() : []));
  }, []);

  if (history.length < 2) return null;

  const LEVEL_PCT: Record<string, number> = { STABLE:22, ELEVATED:44, ESCALATING:70, CRITICAL:100 };
  const BAR_H = 90; // px — the bar zone height

  function handleClick(s: SitrepSummary) {
    if (!onNavigate || s.id === currentId) return;
    setLoading(s.id);
    apiFetch(`${API_BASE}/sitreps/${s.id}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.sitrep) onNavigate(data.sitrep); })
      .finally(() => setLoading(null));
  }

  // Build SVG trajectory line points
  const pts = history.map((s, i) => {
    const pct = LEVEL_PCT[s.escalation_level] ?? 22;
    const y   = BAR_H - (BAR_H * pct / 100);
    const x   = (i + 0.5) * (100 / history.length);
    return `${x}%,${y}`;
  });

  return (
    <div style={{
      borderBottom:"1px solid rgba(255,255,255,0.05)",
      background:"rgba(0,0,0,0.25)",
    }}>
      {/* Header */}
      <div style={{
        display:"flex", alignItems:"center", justifyContent:"space-between",
        padding:"7px 16px 4px",
      }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <span style={{ fontSize:11, letterSpacing:1.5, color:"rgba(255,255,255,0.3)", fontWeight:700 }}>
            SITUATION TIMELINE
          </span>
          <span style={{ fontSize:11, color:"rgba(255,255,255,0.15)", letterSpacing:0.5 }}>
            {history.length} reports · click any to open
          </span>
        </div>
        <div style={{ display:"flex", gap:8 }}>
          {(["STABLE","ELEVATED","ESCALATING","CRITICAL"] as const).map(lv => (
            <div key={lv} style={{ display:"flex", alignItems:"center", gap:3 }}>
              <div style={{ width:5, height:5, borderRadius:1, background:ESCALATION_COLOR[lv], opacity:0.6 }} />
              <span style={{ fontSize:11, color:"rgba(255,255,255,0.2)", letterSpacing:0.4 }}>{lv}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Timeline strip */}
      <div style={{ position:"relative", margin:"0 16px 8px", height:BAR_H }}>

        {/* SVG trajectory line */}
        <svg style={{
          position:"absolute", inset:0, width:"100%", height:"100%",
          pointerEvents:"none", overflow:"visible", zIndex:2,
        }}>
          <polyline
            points={pts.join(" ")}
            fill="none"
            stroke="rgba(255,255,255,0.18)"
            strokeWidth="1.5"
            strokeDasharray="3 3"
          />
          {history.map((s, i) => {
            const pct = LEVEL_PCT[s.escalation_level] ?? 22;
            const y   = BAR_H - (BAR_H * pct / 100);
            const x   = (i + 0.5) * (100 / history.length);
            const lv  = ESCALATION_COLOR[s.escalation_level] ?? "#3fb950";
            return (
              <circle
                key={s.id}
                cx={`${x}%`} cy={y} r={s.id === currentId ? 4 : 2.5}
                fill={s.id === currentId ? lv : `${lv}99`}
                stroke={s.id === currentId ? lv : "none"}
                strokeWidth="1"
              />
            );
          })}
        </svg>

        {/* Segment columns */}
        <div style={{ display:"flex", height:"100%", gap:2 }}>
          {history.map(s => {
            const lv        = ESCALATION_COLOR[s.escalation_level] ?? "#3fb950";
            const pct       = LEVEL_PCT[s.escalation_level] ?? 22;
            const fillH     = `${pct}%`;
            const isCurrent = s.id === currentId;
            const isHovered = hoverId === s.id;
            const isLoading = loading === s.id;
            const tl        = TRIGGER_LABEL[s.trigger] ?? s.trigger?.toUpperCase() ?? "—";
            const tc        = TRIGGER_COLOR[tl] ?? "rgba(100,120,160,0.8)";
            const age       = Math.round((nowMs() - new Date(s.generated_at).getTime()) / 3600000);
            // Shorten headline for display inside the bar
            const shortTitle = s.headline ? s.headline.slice(0, 55) + (s.headline.length > 55 ? "…" : "") : "—";

            return (
              <div
                key={s.id}
                onClick={() => handleClick(s)}
                onMouseEnter={() => setHoverId(s.id)}
                onMouseLeave={() => setHoverId(null)}
                style={{
                  flex: 1, position:"relative", cursor: isCurrent ? "default" : "pointer",
                  borderRadius:3,
                  border: isCurrent
                    ? `1px solid ${lv}77`
                    : isHovered ? `1px solid ${lv}44` : "1px solid rgba(255,255,255,0.04)",
                  transition:"all 0.2s",
                  overflow:"visible",
                  background: isCurrent ? `${lv}10` : isHovered ? `${lv}08` : "rgba(255,255,255,0.02)",
                  boxShadow: isCurrent ? `0 0 12px ${lv}33` : "none",
                }}
              >
                {/* Trigger badge — top */}
                <div style={{
                  position:"absolute", top:4, left:0, right:0,
                  display:"flex", justifyContent:"center", zIndex:1,
                }}>
                  <span style={{
                    fontSize:11, padding:"1px 4px", borderRadius:2,
                    background: isLoading ? "rgba(88,166,255,0.25)" : `${tc.replace("0.9","0.18")}`,
                    color: isLoading ? "#58a6ff" : tc,
                    border:`1px solid ${tc.replace("0.9","0.35")}`,
                    letterSpacing:0.4, fontFamily:"var(--font-mono)", fontWeight:700,
                    whiteSpace:"nowrap",
                  }}>
                    {isLoading ? "…" : tl}
                  </span>
                </div>

                {/* Fill zone — bottom */}
                <div style={{
                  position:"absolute", bottom:0, left:0, right:0,
                  height: fillH, minHeight:18,
                  background: isCurrent
                    ? `linear-gradient(to top, ${lv}55, ${lv}22)`
                    : `linear-gradient(to top, ${lv}33, ${lv}0d)`,
                  borderRadius:"0 0 3px 3px",
                  transition:"height 0.4s ease",
                }}>
                  {/* Time label inside fill */}
                  <div style={{
                    position:"absolute", bottom:3, left:0, right:0, textAlign:"center",
                    fontSize:11, color: isCurrent ? lv : `${lv}cc`,
                    letterSpacing:0.5, fontWeight:700, fontFamily:"var(--font-mono)",
                  }}>
                    {isCurrent ? "NOW" : age < 1 ? "<1H" : `${age}H`}
                  </div>
                </div>

                {/* Headline — middle zone */}
                <div style={{
                  position:"absolute",
                  top:22, bottom:`calc(${fillH} + 2px)`,
                  left:0, right:0,
                  display:"flex", alignItems:"center", justifyContent:"center",
                  padding:"2px 4px",
                  overflow:"hidden",
                }}>
                  <div style={{
                    fontSize:11, lineHeight:1.35,
                    color: isCurrent ? "rgba(255,255,255,0.82)" : "rgba(255,255,255,0.4)",
                    textAlign:"center",
                    display:"-webkit-box", WebkitLineClamp:3, WebkitBoxOrient:"vertical",
                    overflow:"hidden",
                    fontFamily:"var(--font-sans)",
                    transition:"color 0.2s",
                  }}>
                    {isHovered ? (isCurrent ? "↺ current" : "→ open") : shortTitle}
                  </div>
                </div>

                {/* Hover popover */}
                {isHovered && (
                  <div style={{
                    position:"absolute", bottom:"calc(100% + 8px)", left:"50%",
                    transform:"translateX(-50%)",
                    background:"#0d1420",
                    border:`1px solid ${lv}55`,
                    borderRadius:6,
                    padding:"10px 12px",
                    width:220, zIndex:9999,
                    boxShadow:`0 8px 32px rgba(0,0,0,0.6), 0 0 16px ${lv}22`,
                    pointerEvents:"none",
                  }}>
                    {/* Arrow */}
                    <div style={{
                      position:"absolute", bottom:-5, left:"50%", transform:"translateX(-50%)",
                      width:8, height:8, background:"#0d1420",
                      border:`1px solid ${lv}55`, borderTop:"none", borderLeft:"none",
                      rotate:"45deg",
                    }} />
                    {/* Level + time */}
                    <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:6 }}>
                      <span style={{
                        fontSize:11, fontWeight:800, padding:"2px 6px", borderRadius:3,
                        background:`${lv}22`, color:lv, border:`1px solid ${lv}44`,
                        letterSpacing:0.8,
                      }}>
                        {s.escalation_level}
                      </span>
                      <span style={{ fontSize:11, color:"rgba(255,255,255,0.4)", letterSpacing:0.3 }}>
                        {relTime(s.generated_at)}
                      </span>
                      <span style={{
                        fontSize:11, padding:"1px 4px", borderRadius:2, marginLeft:"auto",
                        background:`${tc.replace("0.9","0.15")}`, color:tc,
                        letterSpacing:0.4, fontFamily:"var(--font-mono)",
                      }}>{tl}</span>
                    </div>
                    {/* Full headline */}
                    <div style={{
                      fontSize:12, lineHeight:1.5, color:"rgba(255,255,255,0.85)",
                      marginBottom:8, fontFamily:"var(--font-sans)",
                    }}>
                      {s.headline}
                    </div>
                    {/* Events + CTA */}
                    <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between" }}>
                      <span style={{ fontSize:11, color:"rgba(255,255,255,0.3)" }}>
                        {s.events_analyzed} events analyzed
                      </span>
                      {!isCurrent && (
                        <span style={{ fontSize:11, color:lv, letterSpacing:0.5 }}>
                          click to open →
                        </span>
                      )}
                      {isCurrent && (
                        <span style={{ fontSize:11, color:lv, opacity:0.6 }}>current report</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Trigger label/color maps (module scope — used by Archive + SitrepModal) ──
const TRIGGER_LABEL: Record<string, string> = {
  // legacy names (backward compat with old DB rows)
  time: "4H CYCLE", event_count: "SURGE", critical: "BREAKING", startup: "INIT",
  // new names
  interval: "4H CYCLE", surge: "SURGE", breaking: "BREAKING", convergence: "CONVERGENCE",
  manual: "MANUAL", init: "INIT",
};
const TRIGGER_COLOR: Record<string, string> = {
  "4H CYCLE": "rgba(100,120,160,0.9)", SURGE: "rgba(210,130,40,0.9)",
  BREAKING: "rgba(248,81,73,0.9)", CONVERGENCE: "rgba(80,180,120,0.9)",
  MANUAL: "rgba(100,120,160,0.9)", INIT: "rgba(70,80,90,0.9)",
};

// ── SITREP Archive Modal ──────────────────────────────────────────────────────
function SitrepArchiveModal({
  onClose,
  onOpenSitrep,
}: {
  onClose: () => void;
  onOpenSitrep: (s: Sitrep) => void;
}) {
  const [list, setList] = useState<SitrepSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch(`${API_BASE}/sitreps/?limit=50`)
      .then(r => r.ok ? r.json() : [])
      .then(d => setList(Array.isArray(d) ? d : []))
      .finally(() => setLoading(false));
  }, []);

  function openFull(summary: SitrepSummary) {
    apiFetch(`${API_BASE}/sitreps/${summary.id}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.sitrep) { onClose(); onOpenSitrep(d.sitrep); } });
  }

  return (
    <div onClick={onClose} style={{
      position:"fixed", inset:0, zIndex:9100,
      background:"rgba(0,0,0,0.92)",
      backdropFilter:"blur(8px)",
      display:"flex", alignItems:"center", justifyContent:"center",
      padding:"12px",
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background:"#08101a",
        border:"1px solid rgba(88,166,255,0.2)",
        borderRadius:8,
        width:"100%",
        maxWidth:700,
        maxHeight:"90vh",
        display:"flex",
        flexDirection:"column",
        overflow:"hidden",
        boxShadow:"0 0 80px rgba(88,166,255,0.1), 0 40px 100px rgba(0,0,0,0.95)",
        fontFamily:"var(--font-mono)",
      }}>
        {/* Header */}
        <div style={{
          padding:"14px 20px 12px",
          borderBottom:"1px solid rgba(255,255,255,0.06)",
          display:"flex", justifyContent:"space-between", alignItems:"center",
          background:"rgba(88,166,255,0.04)",
          flexShrink:0,
        }}>
          <div>
            <div style={{ fontSize:12, fontWeight:900, letterSpacing:2.5, color:"#58a6ff" }}>SITREP ARCHIVE</div>
            <div style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.5, marginTop:3, letterSpacing:0.8 }}>
              {list.length} reports stored · generated every 4 hours or on surge/critical events
            </div>
          </div>
          <button onClick={onClose} style={{
            background:"rgba(255,255,255,0.06)", border:"1px solid rgba(255,255,255,0.1)",
            color:"var(--text-secondary)", cursor:"pointer", borderRadius:4, width:28, height:28,
            display:"flex", alignItems:"center", justifyContent:"center", fontSize:14,
          }}>✕</button>
        </div>

        {/* Timeline */}
        <div style={{ overflowY:"auto", flex:1 }}>
          {loading && (
            <div style={{ padding:"24px", textAlign:"center", fontSize:11, color:"var(--text-secondary)", opacity:0.5 }}>
              Loading archive…
            </div>
          )}
          {!loading && list.length === 0 && (
            <div style={{ padding:"24px", textAlign:"center", fontSize:11, color:"var(--text-secondary)", opacity:0.5 }}>
              No SITREPs archived yet
            </div>
          )}
          {list.map((s, i) => {
            const lc = ESCALATION_COLOR[s.escalation_level] ?? "#3fb950";
            const dt = new Date(s.generated_at);
            const dateStr = dt.toLocaleDateString("en-US", { month:"short", day:"numeric", year:"numeric" });
            const timeStr = dt.toLocaleTimeString("en-US", { hour:"2-digit", minute:"2-digit", hour12:false });
            return (
              <div
                key={s.id}
                onClick={() => openFull(s)}
                style={{
                  display:"flex", alignItems:"flex-start", gap:12,
                  padding:"11px 20px",
                  borderBottom:"1px solid rgba(255,255,255,0.04)",
                  cursor:"pointer",
                  transition:"background 0.15s",
                }}
                onMouseEnter={el => (el.currentTarget.style.background = "rgba(88,166,255,0.04)")}
                onMouseLeave={el => (el.currentTarget.style.background = "transparent")}
              >
                {/* Timeline connector */}
                <div style={{ display:"flex", flexDirection:"column", alignItems:"center", flexShrink:0, paddingTop:2 }}>
                  <div style={{ width:10, height:10, borderRadius:"50%", background:lc, boxShadow:`0 0 8px ${lc}88`, flexShrink:0 }} />
                  {i < list.length-1 && <div style={{ width:1, flex:1, minHeight:20, background:"rgba(255,255,255,0.06)", marginTop:3 }} />}
                </div>

                {/* Content */}
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:4, flexWrap:"wrap" as const }}>
                    <span style={{
                      fontSize:11, fontWeight:800, padding:"2px 8px", borderRadius:3,
                      background:`${lc}18`, color:lc, border:`1px solid ${lc}44`, letterSpacing:1,
                    }}>{s.escalation_level}</span>
                    <span style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.6 }}>{dateStr} {timeStr}</span>
                    {(() => {
                      const tl = TRIGGER_LABEL[s.trigger] ?? s.trigger.toUpperCase();
                      const tc = TRIGGER_COLOR[tl] ?? "rgba(150,150,150,0.6)";
                      return (
                        <span style={{
                          fontSize:11, padding:"1px 6px", borderRadius:3,
                          background:`${tc.replace("0.9","0.12")}`, color:tc.replace("0.9","1"),
                          border:`1px solid ${tc.replace("0.9","0.3")}`, letterSpacing:0.8,
                        }}>{tl}</span>
                      );
                    })()}
                    <span style={{ fontSize:11, color:"rgba(255,255,255,0.25)" }}>{s.events_analyzed} events analyzed</span>
                  </div>
                  <div style={{
                    fontSize:12, lineHeight:1.45, color:"var(--text-primary)", opacity:0.85,
                    fontFamily:"var(--font-sans)", overflow:"hidden", textOverflow:"ellipsis",
                    display:"-webkit-box", WebkitLineClamp:2, WebkitBoxOrient:"vertical" as any,
                  }}>
                    {s.headline}
                  </div>
                </div>

                {/* Open arrow */}
                <div style={{ fontSize:12, color:"rgba(88,166,255,0.4)", flexShrink:0, paddingTop:4 }}>↗</div>
              </div>
            );
          })}
        </div>

        <div style={{ padding:"8px 20px", borderTop:"1px solid rgba(255,255,255,0.05)", fontSize:11, color:"rgba(255,255,255,0.2)", letterSpacing:0.8 }}>
          All times UTC · Claude Sonnet analysis · Non-partisan structural methodology
        </div>
      </div>
    </div>
  );
}

// ── Main SITREP Modal ─────────────────────────────────────────────────────────
function SitrepModal({
  sitrep,
  onClose,
  onOpenArchive,
  onNavigate,
}: {
  sitrep: Sitrep;
  onClose: () => void;
  onOpenArchive: () => void;
  onNavigate?: (s: Sitrep) => void;
}) {
  const level  = sitrep.escalation_level ?? "STABLE";
  const lc     = ESCALATION_COLOR[level] ?? "#58a6ff";
  const isCrit = level === "CRITICAL" || level === "ESCALATING";
  const ageStr = relTime(sitrep.generated_at);

  // Fetch source events once — shared between panel + inline badges
  const [srcEvents, setSrcEvents]   = useState<SourceEvent[]>([]);
  const [srcLoading, setSrcLoading] = useState(true);
  const [highlightId, setHighlightId] = useState<number | null>(null);
  // Extra events cited in bullets but not in the key-10 panel
  const [extraEvents, setExtraEvents] = useState<SourceEvent[]>([]);

  useEffect(() => {
    setSrcLoading(true);
    apiFetch(`${API_BASE}/sitreps/${sitrep.id}/events`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setSrcEvents(d.events ?? []); })
      .finally(() => setSrcLoading(false));
  }, [sitrep.id]);

  // After key events load, find all cited IDs across all bullet text,
  // then batch-fetch any that aren't already in the key-10 set.
  useEffect(() => {
    if (srcLoading) return;
    const allText = [
      sitrep.situation, sitrep.escalation_text, sitrep.economic_exposure,
      sitrep.humanitarian_ground, sitrep.game_theory,
    ].filter(Boolean).join("\n");
    const citedIds = new Set(parseSrcIds(allText));
    const keyIds = new Set(srcEvents.map(e => e.id));
    const missing = [...citedIds].filter(id => !keyIds.has(id));
    if (missing.length === 0) { setExtraEvents([]); return; }
    apiFetch(`${API_BASE}/events/batch?ids=${missing.join(",")}`)
      .then(r => r.ok ? r.json() : [])
      .then((evts: SourceEvent[]) => setExtraEvents(evts.map((e: any) => ({
        ...e,
        network: e.source?.startsWith("x_") || e.source?.includes("twitter") ? "X"
                : e.source?.startsWith("tg_") || e.source?.includes("telegram") ? "TG" : "RSS",
      }))));
  }, [srcLoading, srcEvents, sitrep.id]);

  const eventsById = useMemo(
    () => new Map([...srcEvents, ...extraEvents].map(e => [e.id, e])),
    [srcEvents, extraEvents]
  );

  function scrollToEvent(id: number) {
    const el = document.getElementById(`src-evt-${id}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setHighlightId(id);
      setTimeout(() => setHighlightId(null), 2000);
    }
  }

  const SECTIONS = [
    { id:"situation",    icon:"◎", label:"SITUATION",             sub:"Ground truth — what is confirmed vs claimed",    content:sitrep.situation,           color:"#58a6ff", bg:"rgba(88,166,255,0.03)" },
    { id:"escalation",   icon:"△", label:"ESCALATION TRAJECTORY", sub:"Direction and structural threshold indicators",  content:sitrep.escalation_text,     color:lc,        bg:`${lc}06` },
    { id:"economic",     icon:"◈", label:"ECONOMIC EXPOSURE",     sub:"Energy, shipping, finance & commodity impacts",  content:sitrep.economic_exposure,   color:"#d29922", bg:"rgba(210,153,34,0.03)" },
    { id:"humanitarian", icon:"✦", label:"HUMANITARIAN & GROUND", sub:"Civilians, medical, water, food & infrastructure", content:sitrep.humanitarian_ground, color:"#ff8c42", bg:"rgba(255,140,66,0.03)" },
    { id:"game",         icon:"◇", label:"GAME THEORY",           sub:"Structural incentives driving actor behaviour",  content:sitrep.game_theory,         color:"#a78bfa", bg:"rgba(167,139,250,0.03)" },
    { id:"history",      icon:"◑", label:"HISTORICAL ANALOGUE",   sub:"Conditional analogue; compare differences and limitations",     content:sitrep.historical_analogue, color:"#3fb950", bg:"rgba(63,185,80,0.03)" },
  ];

  function formatBulletText(text: string): React.ReactNode {
    const cleaned = stripSrcCitation(text);
    const srcIds  = parseSrcIds(text);
    const parts   = cleaned.split(/(\b[A-Z][A-Z\/&\s]{2,25}[A-Z]\s*—)/);
    const formatted = parts.length <= 1
      ? cleaned
      : parts.map((p, i) =>
          /[A-Z]{2,}.*—/.test(p)
            ? <strong key={i} style={{ fontWeight:700, letterSpacing:0.3 }}>{p}</strong>
            : p
        );

    return (
      <span>
        {formatted}
        {srcIds.length > 0 && srcIds.map(id => {
          const evt   = eventsById.get(id);
          // Short label: strip x_ / rss_ / tg_ prefix, truncate to 12 chars
          const rawCh = evt?.channel_name || evt?.source || String(id);
          const label = rawCh.replace(/^(x_|rss_x?_?|tg_)/i, "").slice(0, 14);
          const nc    = evt ? netColor(evt.network ?? "RSS") : "#58a6ff";
          const tip   = evt
            ? `${evt.channel_name} · ${evt.location_name ?? "—"} · sev ${evt.severity} · ${relTime(evt.timestamp)}`
            : `Event #${id}`;

          return evt?.source_url ? (
            // Has a URL — clicking opens source directly
            <a
              key={id}
              href={safeUrl(evt.source_url)}
              target="_blank"
              rel="noopener noreferrer"
              title={tip}
              onClick={e => { e.stopPropagation(); scrollToEvent(id); }}
              style={{
                marginLeft:5, fontSize:11, padding:"1px 6px", borderRadius:3,
                background:`${nc}14`, color:nc,
                border:`1px solid ${nc}38`,
                fontFamily:"var(--font-mono)", verticalAlign:"middle",
                letterSpacing:0.2, cursor:"pointer", textDecoration:"none",
                display:"inline-flex", alignItems:"center", gap:3,
                transition:"background 0.12s",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = `${nc}28`)}
              onMouseLeave={e => (e.currentTarget.style.background = `${nc}14`)}
            >
              <span style={{ opacity:0.55, fontSize:11 }}>↗</span>{label}
            </a>
          ) : (
            // No URL — clicking scrolls to the event in the panel
            <span
              key={id}
              title={tip}
              onClick={e => { e.stopPropagation(); scrollToEvent(id); }}
              style={{
                marginLeft:5, fontSize:11, padding:"1px 6px", borderRadius:3,
                background:`${nc}14`, color:nc,
                border:`1px solid ${nc}38`,
                fontFamily:"var(--font-mono)", verticalAlign:"middle",
                letterSpacing:0.2, cursor:"pointer",
                display:"inline-flex", alignItems:"center", gap:3,
                transition:"background 0.12s",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = `${nc}28`)}
              onMouseLeave={e => (e.currentTarget.style.background = `${nc}14`)}
            >
              <span style={{ opacity:0.55, fontSize:11 }}>⟢</span>{label}
            </span>
          );
        })}
      </span>
    );
  }

  function renderField(text: string, color: string): React.ReactNode {
    if (!text?.trim()) {
      return <div style={{ padding:"10px 16px", fontSize:12, color:"var(--text-secondary)", fontStyle:"italic", opacity:0.4 }}>No confirmed data in current event window</div>;
    }
    const lines = text.split("\n").map(l => l.replace(/^[•▸]\s*/,"").trim()).filter(Boolean);
    if (lines.length <= 1) {
      return <div style={{ padding:"10px 16px", fontSize:12.5, lineHeight:1.65, color:"var(--text-primary)", opacity:0.9, fontFamily:"var(--font-sans)" }}>{formatBulletText(text)}</div>;
    }
    return (
      <div style={{ padding:"4px 0" }}>
        {lines.map((line, i) => (
          <div key={i} style={{
            display:"flex", alignItems:"flex-start", padding:"5px 16px",
            borderBottom: i < lines.length-1 ? "1px solid rgba(255,255,255,0.03)" : "none",
          }}>
            <div style={{ width:2, minHeight:14, borderRadius:1, background:color, opacity:0.65, flexShrink:0, marginTop:5, marginRight:10 }} />
            <div style={{ fontSize:12.5, lineHeight:1.65, color:"var(--text-primary)", opacity:0.92, fontFamily:"var(--font-sans)", flex:1 }}>
              {formatBulletText(line)}
            </div>
          </div>
        ))}
      </div>
    );
  }

  const levelIdx  = { STABLE:0, ELEVATED:1, ESCALATING:2, CRITICAL:3 }[level] ?? 0;
  const STEPS     = ["STABLE","ELEVATED","ESCALATING","CRITICAL"];
  const STEP_COLS = ["#3fb950","#d29922","#f0883e","#f85149"];

  return (
    <div onClick={onClose} style={{
      position:"fixed", inset:0, zIndex:9000,
      background:"rgba(0,0,0,0.90)",
      backdropFilter:"blur(6px)",
      display:"flex", alignItems:"center", justifyContent:"center",
      padding:"12px",
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background:"linear-gradient(180deg, #080d18 0%, #060a12 100%)",
        border:`1px solid ${lc}28`,
        borderRadius:8,
        width:"100%",
        maxWidth:900,
        maxHeight:"94vh",
        display:"flex",
        flexDirection:"column",
        overflow:"hidden",
        boxShadow:`0 0 100px ${lc}15, 0 0 30px ${lc}08, 0 40px 100px rgba(0,0,0,0.95)`,
        fontFamily:"var(--font-mono)",
      }}>
        {/* Top accent bar */}
        <div style={{
          height:3, flexShrink:0,
          background:`linear-gradient(90deg, transparent 0%, ${lc}99 25%, ${lc} 50%, ${lc}99 75%, transparent 100%)`,
          animation: isCrit ? "threatPulse 1.6s ease-in-out infinite" : undefined,
        }} />

        {/* ── HEADER ── */}
        <div style={{
          padding:"16px 20px 14px",
          background:`linear-gradient(180deg, ${lc}0c 0%, transparent 100%)`,
          flexShrink:0,
          borderBottom:"1px solid rgba(255,255,255,0.05)",
        }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:12 }}>
            <div style={{ display:"flex", alignItems:"center", gap:10, flexWrap:"wrap" as const }}>
              {/* Escalation badge */}
              <div style={{
                padding:"5px 14px", borderRadius:4,
                background:`${lc}1a`, border:`1px solid ${lc}55`,
                display:"flex", alignItems:"center", gap:8,
                boxShadow:`0 0 16px ${lc}20`,
              }}>
                <div style={{
                  width:9, height:9, borderRadius:"50%", background:lc,
                  boxShadow:`0 0 12px ${lc}`,
                  animation: isCrit ? "statusPulseRed 1.2s ease-in-out infinite" : "statusPulse 2.5s ease-in-out infinite",
                }} />
                <span style={{ fontSize:13, fontWeight:900, color:lc, letterSpacing:3, textShadow:`0 0 16px ${lc}99` }}>{level}</span>
              </div>
              <div style={{ fontSize:11, color:"var(--text-secondary)", letterSpacing:0.8 }}>
                SITREP #{sitrep.id}
                <span style={{ color:"rgba(88,166,255,0.6)" }}> · {ageStr}</span>
                <span style={{ opacity:0.4 }}> · {sitrep.events_analyzed} events · </span>
                <span style={{ opacity:0.7, color: TRIGGER_COLOR[TRIGGER_LABEL[sitrep.trigger] ?? sitrep.trigger.toUpperCase()] ?? "rgba(150,150,150,0.7)" }}>
                  {TRIGGER_LABEL[sitrep.trigger] ?? sitrep.trigger.toUpperCase()}
                </span>
              </div>
            </div>

            <div style={{ display:"flex", alignItems:"center", gap:6 }}>
              <button
                onClick={e => { e.stopPropagation(); onOpenArchive(); }}
                style={{
                  background:"rgba(88,166,255,0.07)", border:"1px solid rgba(88,166,255,0.2)",
                  color:"rgba(88,166,255,0.8)", cursor:"pointer", borderRadius:4,
                  padding:"4px 10px", fontSize:11, fontFamily:"var(--font-mono)", letterSpacing:1,
                  fontWeight:700, display:"flex", alignItems:"center", gap:4,
                }}
              >
                ⊞ ARCHIVE
              </button>
              <button onClick={onClose} style={{
                background:"rgba(255,255,255,0.06)", border:"1px solid rgba(255,255,255,0.1)",
                color:"var(--text-secondary)", cursor:"pointer",
                borderRadius:4, width:28, height:28,
                display:"flex", alignItems:"center", justifyContent:"center", fontSize:14, flexShrink:0,
              }}>✕</button>
            </div>
          </div>

          {/* Escalation progress steps */}
          <div style={{ display:"flex", gap:3, marginBottom:12 }}>
            {STEPS.map((step, i) => {
              const active  = i <= levelIdx;
              const current = i === levelIdx;
              return (
                <div key={step} style={{ flex:1, display:"flex", flexDirection:"column", gap:3 }}>
                  <div style={{
                    height:4, borderRadius:2,
                    background: active ? STEP_COLS[i] : "rgba(255,255,255,0.06)",
                    boxShadow: current ? `0 0 10px ${STEP_COLS[i]}` : "none",
                    transition:"all 0.5s ease",
                  }} />
                  <span style={{ fontSize:11, letterSpacing:1, color: current ? STEP_COLS[i] : "rgba(255,255,255,0.18)", fontWeight: current ? 900 : 400, textAlign:"center" }}>{step}</span>
                </div>
              );
            })}
          </div>

          {/* Headline */}
          <div style={{ fontSize:16, fontWeight:700, lineHeight:1.45, color:"var(--text-primary)", fontFamily:"var(--font-sans)", textShadow: isCrit ? `0 0 40px ${lc}44` : "none" }}>
            {sitrep.headline}
          </div>
        </div>

        {/* ── ESCALATION HISTORY STRIP ── */}
        <EscalationHistoryStrip currentId={sitrep.id} accentColor={lc} onNavigate={onNavigate} />

        {/* ── SCROLLABLE BODY ── */}
        <div style={{ overflowY:"auto", flex:1 }}>

          {/* ── SOURCE INTELLIGENCE PANEL ── */}
          <SourceEventsPanel events={srcEvents} loading={srcLoading} highlightId={highlightId} accentColor={lc} />

          {/* ── SITUATION (full width) ── */}
          {[SECTIONS[0]].map(({ id, icon, label, sub, content, color, bg }) => (
            <div key={id} style={{ borderLeft:`3px solid ${color}45`, borderBottom:"1px solid rgba(255,255,255,0.04)", background:bg }}>
              <div style={{ display:"flex", alignItems:"center", gap:8, padding:"9px 16px 5px" }}>
                <span style={{ fontSize:12, color, fontWeight:800, textShadow:`0 0 8px ${color}55` }}>{icon}</span>
                <div>
                  <div style={{ fontSize:11, fontWeight:800, letterSpacing:1.8, color, textTransform:"uppercase" as const }}>{label}</div>
                  <div style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.55, letterSpacing:0.4, marginTop:1 }}>{sub}</div>
                </div>
              </div>
              {renderField(content ?? "", color)}
            </div>
          ))}

          {/* ── ESCALATION TRAJECTORY (full width) ── */}
          {[SECTIONS[1]].map(({ id, icon, label, sub, content, color, bg }) => (
            <div key={id} style={{ borderLeft:`3px solid ${color}45`, borderBottom:"1px solid rgba(255,255,255,0.04)", background:bg }}>
              <div style={{ display:"flex", alignItems:"center", gap:8, padding:"9px 16px 5px" }}>
                <span style={{ fontSize:12, color, fontWeight:800, textShadow:`0 0 8px ${color}55` }}>{icon}</span>
                <div>
                  <div style={{ fontSize:11, fontWeight:800, letterSpacing:1.8, color, textTransform:"uppercase" as const }}>{label}</div>
                  <div style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.55, letterSpacing:0.4, marginTop:1 }}>{sub}</div>
                </div>
              </div>
              {renderField(content ?? "", color)}
            </div>
          ))}

          {/* ── ECONOMIC + HUMANITARIAN (two column) ── */}
          <div style={{ display:"flex", gap:1 }}>
            {[SECTIONS[2], SECTIONS[3]].map(({ id, icon, label, sub, content, color, bg }) => (
              <div key={id} style={{ flex:1, borderLeft:`3px solid ${color}45`, borderBottom:"1px solid rgba(255,255,255,0.04)", background:bg }}>
                <div style={{ display:"flex", alignItems:"center", gap:8, padding:"9px 14px 5px" }}>
                  <span style={{ fontSize:12, color, fontWeight:800, textShadow:`0 0 8px ${color}55` }}>{icon}</span>
                  <div>
                    <div style={{ fontSize:11, fontWeight:800, letterSpacing:1.8, color, textTransform:"uppercase" as const }}>{label}</div>
                    <div style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.55, letterSpacing:0.4, marginTop:1 }}>{sub}</div>
                  </div>
                </div>
                {renderField(content ?? "", color)}
              </div>
            ))}
          </div>

          {/* ── GAME THEORY + HISTORICAL ANALOGUE (full width) ── */}
          {[SECTIONS[4], SECTIONS[5]].map(({ id, icon, label, sub, content, color, bg }) => (
            <div key={id} style={{ borderLeft:`3px solid ${color}45`, borderBottom:"1px solid rgba(255,255,255,0.04)", background:bg }}>
              <div style={{ display:"flex", alignItems:"center", gap:8, padding:"9px 16px 5px" }}>
                <span style={{ fontSize:12, color, fontWeight:800, textShadow:`0 0 8px ${color}55` }}>{icon}</span>
                <div>
                  <div style={{ fontSize:11, fontWeight:800, letterSpacing:1.8, color, textTransform:"uppercase" as const }}>{label}</div>
                  <div style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.55, letterSpacing:0.4, marginTop:1 }}>{sub}</div>
                </div>
              </div>
              {renderField(content ?? "", color)}
            </div>
          ))}

          {/* Footer */}
          <div style={{
            padding:"10px 16px 14px",
            display:"flex", justifyContent:"space-between", alignItems:"center",
            fontSize:11, color:"var(--text-secondary)", opacity:0.3, letterSpacing:0.8,
            borderTop:"1px solid rgba(255,255,255,0.04)", marginTop:2,
          }}>
            <span>Generated {new Date(sitrep.generated_at).toUTCString()} · Claude Sonnet structural analysis · #{sitrep.id}</span>
            <button
              onClick={e => { e.stopPropagation(); onOpenArchive(); }}
              style={{
                background:"none", border:"1px solid rgba(255,255,255,0.1)",
                color:"rgba(255,255,255,0.3)", cursor:"pointer", borderRadius:3,
                padding:"3px 8px", fontSize:11, fontFamily:"var(--font-mono)", letterSpacing:1,
              }}
            >VIEW ALL SITREPS ↗</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main StrategicPulseBar ────────────────────────────────────────────────────
interface StrategicPulseBarProps {
  events: ConflictEvent[];
  onSitrepKeyEvents?: (ids: number[]) => void;
  onEscalationChange?: (level: "STABLE"|"ELEVATED"|"ESCALATING"|"CRITICAL") => void;
}

export function StrategicPulseBar({ events, onSitrepKeyEvents, onEscalationChange }: StrategicPulseBarProps) {
  const [sitrep,       setSitrep]       = useState<Sitrep | null>(null);
  const [sitrepOpen,   setSitrepOpen]   = useState(false);
  const [archiveOpen,  setArchiveOpen]  = useState(false);
  const [archiveCount, setArchiveCount] = useState<number>(0);
  const pollRef = useRef<ReturnType<typeof setInterval>>(undefined);

  // Poll latest SITREP every 2 minutes
  useEffect(() => {
    const fetch_ = async () => {
      try {
        const res = await apiFetch(`${API_BASE}/sitreps/latest`);
        if (res.ok) {
          const data = await res.json();
          if (data.sitrep) {
            setSitrep(data.sitrep);
            onEscalationChange?.(data.sitrep.escalation_level ?? "STABLE");
          }
        }
      } catch { /* offline */ }
    };
    fetch_();
    pollRef.current = setInterval(fetch_, 120_000);
    return () => clearInterval(pollRef.current);
  }, []);

  // Fetch archive count once
  useEffect(() => {
    apiFetch(`${API_BASE}/sitreps/?limit=50`)
      .then(r => r.ok ? r.json() : [])
      .then(d => setArchiveCount(Array.isArray(d) ? d.length : 0));
  }, []);

  const now    = nowMs();
  const last6h = events.filter(e => now - new Date(e.timestamp).getTime() < 6 * 3600000);
  const confirmed = last6h.filter(hasMultipleReports);
  const confRate  = last6h.length > 0 ? Math.round((confirmed.length / last6h.length) * 100) : 0;
  const last15m   = events.filter(e => now - new Date(e.timestamp).getTime() < 15 * 60_000).length;
  const evtPerHr  = Math.round(last15m * 4);

  const level      = sitrep?.escalation_level ?? "STABLE";
  const levelColor = ESCALATION_COLOR[level] ?? "#3fb950";
  const sitrepAgeStr = sitrep ? relTime(sitrep.generated_at) : "pending";

  const chokepoints = CHOKEPOINTS.map(cp => ({ ...cp, status: getChokepointStatus(events, cp) }));

  function openSitrepModal() {
    setSitrepOpen(true);
    if (onSitrepKeyEvents && sitrep?.key_event_ids?.length) {
      onSitrepKeyEvents(sitrep.key_event_ids);
    }
  }

  return (
    <>
      <div style={{
        gridArea:"pulse",
        background:"#06090f",
        borderBottom:"1px solid rgba(88,166,255,0.10)",
        display:"flex", alignItems:"center",
        padding:"0 16px", gap:0, height:38,
        fontFamily:"var(--font-mono)",
        overflowX:"auto", overflowY:"hidden",
        flexShrink:0,
      }}>
        {/* Verification stats */}
        <div style={{ display:"flex", alignItems:"center", gap:10, paddingRight:14, flexShrink:0 }}>
          <span style={{ fontSize:11, letterSpacing:1.5, color:"var(--text-secondary)", opacity:0.5 }}>MULTI-REPORT</span>
          <span style={{ fontSize:13, fontWeight:700, color:"#3fb950" }}>{confirmed.length}</span>
          <span style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.7 }}>/ {last6h.length}</span>
          <span style={{
            fontSize:11, padding:"1px 6px", borderRadius:3, fontWeight:700,
            background: confRate >= 10 ? "rgba(63,185,80,0.15)" : "rgba(210,153,34,0.12)",
            color: confRate >= 10 ? "#3fb950" : "#d29922",
            border:`1px solid ${confRate >= 10 ? "rgba(63,185,80,0.3)" : "rgba(210,153,34,0.3)"}`,
          }}>{confRate}% CONF</span>
        </div>

        <div style={{ width:1, height:18, background:"rgba(88,166,255,0.08)", margin:"0 12px", flexShrink:0 }} />

        {/* Chokepoints */}
        <div style={{ display:"flex", alignItems:"center", gap:8, paddingRight:14, flexShrink:0 }}>
          <span style={{ fontSize:11, letterSpacing:1.5, color:"var(--text-secondary)", opacity:0.5 }}>CHOKEPOINTS</span>
          {chokepoints.map(({ id, label, status }) => (
            <div key={id} style={{ display:"flex", alignItems:"center", gap:4 }}>
              <span style={{
                width:6, height:6, borderRadius:"50%", flexShrink:0,
                background:CP_COLOR[status],
                boxShadow: status !== "clear" ? `0 0 6px ${CP_COLOR[status]}` : "none",
                animation: status === "active" ? "statusPulse 1.2s ease-in-out infinite" : "none",
              }} />
              <span style={{ fontSize:11, fontWeight: status !== "clear" ? 700 : 400, color:CP_COLOR[status], letterSpacing:0.5 }}>{label}</span>
            </div>
          ))}
        </div>

        <div style={{ width:1, height:18, background:"rgba(88,166,255,0.08)", margin:"0 12px", flexShrink:0 }} />

        {/* SITREP teaser */}
        <div style={{ flex:1, minWidth:0, display:"flex", alignItems:"center", gap:10, overflow:"hidden" }}>
          <span style={{
            fontSize:11, padding:"2px 7px", borderRadius:3, fontWeight:800,
            background:`${levelColor}18`, color:levelColor,
            border:`1px solid ${levelColor}44`, letterSpacing:1.5, flexShrink:0,
            animation: level === "CRITICAL" || level === "ESCALATING" ? "statusPulse 2s ease-in-out infinite" : "none",
          }}>● {level}</span>

          {sitrep ? (
            <button onClick={openSitrepModal} style={{
              background:"none", border:"none", cursor:"pointer",
              color:"var(--text-primary)", textAlign:"left", padding:0,
              minWidth:0, overflow:"hidden",
              display:"flex", alignItems:"center", gap:8, flex:1,
            }}>
              <span style={{
                fontSize:12, color:"var(--text-primary)", opacity:0.85,
                overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap",
                fontFamily:"var(--font-sans)",
              }}>{sitrep.headline}</span>
              <span style={{ fontSize:11, color:"#58a6ff", letterSpacing:0.5, flexShrink:0, opacity:0.8 }}>
                SITREP {sitrepAgeStr} ↗
              </span>
            </button>
          ) : (
            <span style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.5, fontFamily:"var(--font-sans)" }}>
              SITREP generating…
            </span>
          )}
        </div>

        <div style={{ width:1, height:18, background:"rgba(88,166,255,0.08)", margin:"0 12px", flexShrink:0 }} />

        {/* Archive button */}
        <button
          onClick={() => setArchiveOpen(true)}
          style={{
            background:"none", border:"1px solid rgba(88,166,255,0.15)",
            color:"rgba(88,166,255,0.6)", cursor:"pointer", borderRadius:3,
            padding:"2px 8px", fontSize:11, fontFamily:"var(--font-mono)", letterSpacing:1,
            fontWeight:700, flexShrink:0, marginRight:10,
          }}
        >
          ⊞ {archiveCount > 0 ? archiveCount : ""} ARCHIVE
        </button>

        {/* Event rate */}
        <div style={{ display:"flex", alignItems:"center", gap:8, flexShrink:0 }}>
          <span style={{
            fontSize:13, fontWeight:700,
            color: evtPerHr >= 60 ? "#f85149" : evtPerHr >= 30 ? "#d29922" : "#58a6ff",
          }}>{evtPerHr}</span>
          <span style={{ fontSize:11, color:"var(--text-secondary)", opacity:0.6 }}>EVT/HR</span>
          {evtPerHr >= 40 && (
            <span style={{
              fontSize:11, padding:"1px 5px", borderRadius:3, fontWeight:700,
              background:"rgba(248,81,73,0.12)", color:"#f85149",
              border:"1px solid rgba(248,81,73,0.3)",
              animation:"pulse 1.5s ease-in-out infinite",
            }}>SURGE</span>
          )}
        </div>
      </div>

      {/* SITREP modal */}
      {sitrepOpen && sitrep && (
        <SitrepModal
          sitrep={sitrep}
          onClose={() => setSitrepOpen(false)}
          onOpenArchive={() => { setSitrepOpen(false); setArchiveOpen(true); }}
          onNavigate={s => setSitrep(s)}
        />
      )}

      {/* Archive modal */}
      {archiveOpen && (
        <SitrepArchiveModal
          onClose={() => setArchiveOpen(false)}
          onOpenSitrep={s => { setSitrep(s); setSitrepOpen(true); }}
        />
      )}
    </>
  );
}
