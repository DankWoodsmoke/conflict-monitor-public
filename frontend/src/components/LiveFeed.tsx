import { severityLabel,reportSourceKind } from "../lib/events";
import { safeUrl } from "../lib/runtime";
import { EvidenceDetails } from "./EvidenceDetails";
import { nowMs } from "../lib/clock";
import {hasUsableReportCoordinates} from "../lib/reportPosition";
import {recentReports} from "../lib/reportPresentation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ConflictEvent } from "../types/event";
import { hasMultipleReports, isViralAmplification, getNetworks, NETWORK_META } from "../utils/verification";

// ── Channel metadata ──────────────────────────────────────────────────────────
interface ChanMeta { flag: string; label: string; rel: number; tip: string }
const CHAN: Record<string, ChanMeta> = {
  CIG_telegram:          { flag: "🔍", rel: 5, label: "CIG",            tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  GeoConfirmed:          { flag: "📍", rel: 5, label: "GeoConfirmed",   tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  AuroraIntel:           { flag: "🌐", rel: 4, label: "Aurora Intel",   tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  OSINTdefender:         { flag: "🌐", rel: 4, label: "OSINT Defender", tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  OSINTWarfare:          { flag: "🗺️", rel: 4, label: "OSINT Warfare",  tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  ourwarstoday:          { flag: "⚖️", rel: 4, label: "Our Wars Today", tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  MATA_osint:            { flag: "✈️", rel: 3, label: "MATA Alliance",  tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  Intel_Sky:             { flag: "🛰️", rel: 3, label: "IntelSky",       tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  MilitaryOSINT:         { flag: "🎖️", rel: 3, label: "Mil OSINT",      tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  inabornintel:          { flag: "📡", rel: 3, label: "In A Born Intel", tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  IranIntl_En:           { flag: "📰", rel: 3, label: "Iran Intl",      tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  IsraelRadar_com:       { flag: "📰", rel: 3, label: "Israel Radar",   tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  QudsNen:               { flag: "📰", rel: 3, label: "Quds News",      tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  Middle_East_Spectator: { flag: "📰", rel: 3, label: "ME Spectator",   tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  warmonitors:           { flag: "⚡", rel: 2, label: "War Monitors",    tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  IntelSlava:            { flag: "📣", rel: 2, label: "Intel Slava Z",   tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  SentDefender:          { flag: "⚡", rel: 2, label: "SentDefender",    tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  reuters:               { flag: "🗞️", rel: 4, label: "Reuters",         tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  bbc_mideast:           { flag: "🗞️", rel: 4, label: "BBC Middle East", tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  ap_news:               { flag: "🗞️", rel: 4, label: "AP News",         tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  the_war_zone:          { flag: "🗞️", rel: 4, label: "The War Zone",    tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  aljazeera:             { flag: "🗞️", rel: 3, label: "Al Jazeera",      tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  times_of_israel:       { flag: "🗞️", rel: 3, label: "Times of Israel", tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  iran_international:    { flag: "🗞️", rel: 3, label: "Iran Intl (RSS)", tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  rfi:                   { flag: "🗞️", rel: 3, label: "RFI",             tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  defense_one:           { flag: "🗞️", rel: 3, label: "Defense One",     tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  middle_east_eye:       { flag: "🗞️", rel: 3, label: "MEE",             tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  x_geoconfirmed:        { flag: "𝕏", rel: 5, label: "GeoConfirmed",    tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  x_lourage_america:     { flag: "𝕏", rel: 4, label: "Lourage America", tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  x_dropsitenews:        { flag: "𝕏", rel: 4, label: "Drop Site",       tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  x_elintnews:           { flag: "𝕏", rel: 4, label: "ELINT News",      tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  x_auroraintel:         { flag: "𝕏", rel: 4, label: "Aurora Intel",    tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  x_osintdefender:       { flag: "𝕏", rel: 4, label: "OSINT Defender",  tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  x_osintwarfare:        { flag: "𝕏", rel: 4, label: "OSINT Warfare",   tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  x_intel_sky:           { flag: "𝕏", rel: 3, label: "IntelSky",        tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  x_osint613:            { flag: "𝕏", rel: 3, label: "Osint613",        tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  "Aurora Intel":        { flag: "🌐", rel: 4, label: "Aurora Intel",   tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  "CIG":                 { flag: "🔍", rel: 5, label: "CIG",            tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  "Intel Slava Z":       { flag: "📣", rel: 2, label: "Intel Slava Z",  tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  "IranIntl":            { flag: "📰", rel: 3, label: "Iran Intl",      tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  "Israel Radar":        { flag: "📰", rel: 3, label: "Israel Radar",   tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  "MidEast Spectator":   { flag: "📰", rel: 3, label: "ME Spectator",   tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  "QudsAlert":           { flag: "📰", rel: 3, label: "Quds Alert",     tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  "WarMonitor":          { flag: "⚡", rel: 2, label: "War Monitor",     tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  "truthtellerftm":      { flag: "📡", rel: 3, label: "TRUTHTELLER",    tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  "TRUTHTELLER":         { flag: "📡", rel: 3, label: "TRUTHTELLER",    tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  "israelradar":         { flag: "📰", rel: 3, label: "Israel Radar",   tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  DropSiteNews:          { flag: "🔍", rel: 4, label: "Drop Site News",  tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  ELINTNews:             { flag: "📡", rel: 4, label: "ELINT News",      tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
  IntelSky:              { flag: "✈️", rel: 3, label: "IntelSky",        tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." },
};

function chanMeta(handle: string): ChanMeta {
  return CHAN[handle] ?? Object.entries(CHAN).find(
    ([k]) => k.toLowerCase() === handle?.toLowerCase()
  )?.[1] ?? { flag: "📡", rel: 3, label: handle || "Unknown", tip: "Curated source entry. Publisher rating is not claim verification; review original evidence." };
}

// ── Constants ────────────────────────────────────────────────────────────────
const TYPE_COLORS: Record<string, string> = {
  unclassified:    "#91b4c5",
  military:        "#ff8f88",
  diplomatic:      "#8fc5ff",
  economic:        "#ffb878",
  cyber:           "#d0adff",
  humanitarian:    "#7ad793",
  protest:         "#eac566",
  thermal_anomaly: "#ffb66b",
};

const TYPE_ICONS: Record<string, string> = {
  unclassified:    "▤",
  military:        "💥",
  diplomatic:      "🤝",
  economic:        "📊",
  cyber:           "💻",
  humanitarian:    "🏥",
  protest:         "✊",
  thermal_anomaly: "🔥",
};

function sevColor(s: number): string {
  if (s >= 9) return "#ff7770";
  if (s >= 7) return "#ff8f88";
  if (s >= 5) return "#ffb878";
  if (s >= 3) return "#eac566";
  return "#a3b9ca";
}

function relColor(r: number | undefined | null): string {
  if (r == null) return "#9aafbd";
  const s = r;
  if (s >= 5) return "#3fb950";
  if (s >= 4) return "#3fb950";
  if (s >= 3) return "#d29922";
  if (s >= 2) return "#f0883e";
  return "#ff8f88";
}

function playBlip() {
  try {
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 880;
    osc.type = "sine";
    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.15);
    osc.onended=()=>{void ctx.close();};
  } catch { /* no audio context */ }
}

// ── Props ────────────────────────────────────────────────────────────────────
interface LiveFeedProps {
  events:        ConflictEvent[];
  allEvents?:    ConflictEvent[];
  onEventClick?: (evt: ConflictEvent) => void;
  selectedEventId?: number | null;
}

// ── Source quality dots ───────────────────────────────────────────────────────
function QualityDots({ score }: { score: number | undefined | null }) {
  if (score == null) return <span title="No calibrated source assessment" style={{fontSize:11,color:"#94a8b6"}}>Unrated</span>;
  const s = Math.max(0, Math.min(5, score));
  const colors = ["#f85149", "#f0883e", "#d29922", "#3fb950", "#3fb950"];
  return (
    <span style={{ display: "inline-flex", gap: 2, alignItems: "center", verticalAlign: "middle" }}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} style={{
          display: "inline-block", width: 4, height: 4, borderRadius: "50%",
          background: i <= s ? colors[Math.min(i - 1, 4)] : "rgba(255,255,255,0.1)",
          flexShrink: 0,
        }} />
      ))}
    </span>
  );
}

// ── Confirmation badge ───────────────────────────────────────────────────────
function ConfBadge({ evt }: { evt: ConflictEvent }) {
  const isSat = reportSourceKind(evt)==="sensor";
  const isCross = hasMultipleReports(evt);
  const isViral = isViralAmplification(evt);
  const count = evt.report_count ?? 1;

  if (isSat) return (
    <span style={{ fontSize: 11, padding: "1px 5px", borderRadius: 2, background: "rgba(13,110,253,0.2)", color: "#9cc8ff", fontWeight: 700, fontFamily: "var(--font-mono)", border: "1px solid rgba(13,110,253,0.4)", whiteSpace: "nowrap" }}>🛰 SAT</span>
  );
  if (isCross) {
    const nets = getNetworks(evt);
    return (
      <span title={"Multiple source records; independence unassessed: " + nets.map(n => NETWORK_META[n]?.short ?? n).join(" + ")} style={{ fontSize: 11, padding: "1px 5px", borderRadius: 2, background: "rgba(63,185,80,0.15)", color: "#8ae2a1", fontWeight: 700, fontFamily: "var(--font-mono)", border: "1px solid rgba(63,185,80,0.4)", cursor: "help", whiteSpace: "nowrap" }}>↗ {count}× REPORTS</span>
    );
  }
  if (isViral) return (
    <span style={{ fontSize: 11, padding: "1px 5px", borderRadius: 2, background: "rgba(210,153,34,0.15)", color: "#f1d078", fontWeight: 700, fontFamily: "var(--font-mono)", border: "1px solid rgba(210,153,34,0.4)", whiteSpace: "nowrap" }}>⚡ {count}×</span>
  );
  return null;
}

// ── Age display ───────────────────────────────────────────────────────────────
function AgeChip({ timestamp }: { timestamp: string }) {
  const ageMs = nowMs() - new Date(timestamp).getTime();
  if(!Number.isFinite(ageMs))return <span>Source time unknown</span>;
  if(ageMs<0)return <span title={timestamp}>Source clock ahead</span>;
  const mins = Math.floor(ageMs / 60000);
  if (mins < 1) return <span style={{ fontSize: 11, color: "#ff8f88", fontWeight: 900, fontFamily: "var(--font-mono)", letterSpacing: 0.5 }}>●&nbsp;NOW</span>;
  if (mins < 5)  return <span style={{ fontSize: 11, color: "#ff8f88", fontWeight: 700, fontFamily: "var(--font-mono)" }}>●&nbsp;{mins}m</span>;
  if (mins < 60) return <span style={{ fontSize: 11, color: "#d29922", fontFamily: "var(--font-mono)" }}>{mins}m ago</span>;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return <span style={{ fontSize: 11, color: "#96a8b8", fontFamily: "var(--font-mono)" }}>{hrs}h ago</span>;
  return <span style={{ fontSize: 11, color: "#8b9eaf", fontFamily: "var(--font-mono)" }}>{Math.floor(hrs / 24)}d ago</span>;
}

// ── Main component ────────────────────────────────────────────────────────────
export function LiveFeed({ events, allEvents, onEventClick, selectedEventId }: LiveFeedProps) {
  const containerRef  = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [newIds, setNewIds]         = useState<Set<number>>(new Set());
  const prevCountRef  = useRef(0);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [filtersOpen, setFiltersOpen]   = useState(false);

  // Filter state
  const [search,       setSearch]       = useState("");
  const [minSev,       setMinSev]       = useState(1);
  const [typeFilter,   setTypeFilter]   = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const [sortMode,     setSortMode]     = useState<"new" | "sev" | "conf">("new");

  // ── New event detection ───────────────────────────────────────────────────
  useEffect(() => {
    if (events.length > prevCountRef.current && prevCountRef.current > 0) {
      const incoming = events.slice(0, events.length - prevCountRef.current);
      setNewIds(new Set(incoming.map((e) => e.id)));
      if (soundEnabled) playBlip();
      const t = setTimeout(() => setNewIds(new Set()), 4000);
      return () => clearTimeout(t);
    }
    prevCountRef.current = events.length;
  }, [events, soundEnabled]);

  useEffect(() => { prevCountRef.current = events.length; }, [events.length]);

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (autoScroll && containerRef.current && sortMode === "new") {
      containerRef.current.scrollTop = 0;
    }
  }, [events.length, autoScroll, sortMode]);

  const handleScroll = useCallback(() => {
    if (!containerRef.current) return;
    setAutoScroll(containerRef.current.scrollTop < 20);
  }, []);

  // ── Live burst stats (always computed from allEvents) ─────────────────────
  const burstStats = useMemo(() => {
    const src = allEvents ?? events;
    const now = nowMs();
    const last15=recentReports(src,now,.25).length;
    const prev15  = src.filter((e) => {
      const age = now - new Date(e.timestamp).getTime();
      return Number.isFinite(age)&&age > 15 * 60000 && age <= 30 * 60000;
    }).length;
    const last60=recentReports(src,now,1).length;
    const perHr   = last60; // already events/hr
    const trend   = last15 > prev15 * 1.25 ? "up" : last15 < prev15 * 0.75 ? "down" : "stable";
    const nets: Record<string, number> = {};
    for (const e of src) {
      const s = e.source ?? "";
      const net = {telegram:"TG",x:"𝕏",rss:"RSS",sensor:"SENSOR",other:"OTHER"}[reportSourceKind(e)];
      nets[net] = (nets[net] ?? 0) + 1;
    }
    return { last15, prev15, perHr, trend, nets };
  }, [allEvents, events]);

  // ── Filtered + sorted event list ──────────────────────────────────────────
  const filteredEvents = useMemo(() => {
    const filtered = events.filter((e) => {
      if (minSev > 1 && (e.severity ?? 0) < minSev) return false;
      if (typeFilter && e.event_type !== typeFilter) return false;
      if (confirmedOnly && !hasMultipleReports(e)) return false;
      if(sourceFilter && reportSourceKind(e)!==sourceFilter)return false;
      if (search.trim()) {
        const q = search.toLowerCase();
        return (e.summary?.toLowerCase().includes(q) || e.location_name?.toLowerCase().includes(q) || e.channel_name?.toLowerCase().includes(q));
      }
      return true;
    });
    if (sortMode === "sev")  return [...filtered].sort((a, b) => (b.severity ?? 0) - (a.severity ?? 0));
    if (sortMode === "conf") return [...filtered].sort((a, b) => {
      const ac = hasMultipleReports(a) ? 2 : (a.report_count ?? 1);
      const bc = hasMultipleReports(b) ? 2 : (b.report_count ?? 1);
      return bc - ac;
    });
    return filtered;
  }, [events, search, minSev, typeFilter, sourceFilter, confirmedOnly, sortMode]);

  const activeFilterCount = (minSev > 1 ? 1 : 0) + (typeFilter ? 1 : 0) + (sourceFilter ? 1 : 0) + (confirmedOnly ? 1 : 0) + (search ? 1 : 0);

  // ── CSS injection ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (document.getElementById("intel-feed-styles")) return;
    const style = document.createElement("style");
    style.id = "intel-feed-styles";
    style.textContent = `
      @keyframes intelSlideIn { from { opacity:0; transform:translateX(12px); } to { opacity:1; transform:translateX(0); } }
      @keyframes intelPulse   { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
      @keyframes intelGlow    { 0%,100% { box-shadow:0 0 0 0 rgba(248,81,73,0); } 50% { box-shadow:0 0 0 4px rgba(248,81,73,0.15); } }
      @keyframes nowBlink     { 50% { opacity:0; } }
      .intel-card:hover { background: rgba(88,166,255,0.05) !important; }
      .intel-card-new  { animation: intelSlideIn 0.3s cubic-bezier(0.2,0,0,1) backwards; }
      .intel-card-crit { animation: intelGlow 2s ease-in-out 3; }
      ::-webkit-scrollbar { width: 3px; } 
      ::-webkit-scrollbar-track { background: transparent; }
      ::-webkit-scrollbar-thumb { background: #1e3a5a; border-radius: 2px; }
    `;
    document.head.appendChild(style);
  }, []);

  const trendColor = burstStats.trend === "up" ? "#f85149" : burstStats.trend === "down" ? "#3fb950" : "#8ea8be";
  const trendArrow = burstStats.trend === "up" ? "↑" : burstStats.trend === "down" ? "↓" : "→";

  return (
    <div className="report-feed" style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden", background: "#04080f" }}>

      {/* ── HEADER ───────────────────────────────────────────────────────── */}
      <div style={{
        padding: "0 12px",
        borderBottom: "1px solid #0d2035",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        height: 48, flexShrink: 0,
        background: "#030c18",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#3fb950", display: "inline-block", animation: undefined, boxShadow: "0 0 6px rgba(63,185,80,0.7)" }} />
          <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: 2, color: "#c0d8f0", fontFamily: "var(--font-mono)" }}>REPORT FEED</span>
          <span style={{ fontSize: 11, color: "#829aae", fontFamily: "var(--font-mono)" }}>
            {activeFilterCount > 0 ? `${filteredEvents.length}/${events.length}` : events.length}
          </span>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <button
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen(v => !v)}
            style={{
              background: filtersOpen ? "rgba(88,166,255,0.12)" : "none",
              border: `1px solid ${filtersOpen || activeFilterCount > 0 ? "rgba(88,166,255,0.5)" : "#0d2035"}`,
              color: filtersOpen || activeFilterCount > 0 ? "#58a6ff" : "#8da3b7",
              fontSize: 11, padding: "2px 7px", borderRadius: 3, cursor: "pointer",
              fontFamily: "var(--font-mono)", fontWeight: 700, letterSpacing: 0.5,
            }}
          >
            {activeFilterCount > 0 ? `FILTER (${activeFilterCount})` : "FILTER"}
          </button>
          <button
            aria-label={soundEnabled ? "Mute report notifications" : "Enable report notifications"}
            aria-pressed={soundEnabled}
            onClick={() => setSoundEnabled(v => !v)}
            style={{
              background: "none",
              border: `1px solid ${soundEnabled ? "rgba(88,166,255,0.5)" : "#0d2035"}`,
              color: soundEnabled ? "#58a6ff" : "#8da3b7",
              fontSize: 11, padding: "2px 7px", borderRadius: 3, cursor: "pointer",
              fontFamily: "var(--font-mono)", fontWeight: 700,
            }}
          >{soundEnabled ? "🔊" : "🔇"}</button>
        </div>
      </div>

      {/* ── LIVE STATS BAR ───────────────────────────────────────────────── */}
      <div style={{
        padding: "5px 12px",
        borderBottom: "1px solid #0a1a2a",
        background: "#030c18",
        display: "flex", alignItems: "center", gap: 10,
        flexShrink: 0,
        fontFamily: "var(--font-mono)",
      }}>
        {/* Rate */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 32 }}>
          <span style={{ fontSize: 14, fontWeight: 800, color: "#58a6ff", lineHeight: 1 }}>{burstStats.perHr}</span>
          <span style={{ fontSize: 11, color: "#829aae", letterSpacing: 0.5 }}>RPTS/HR</span>
        </div>
        <div style={{ width: 1, background: "#0d2035", alignSelf: "stretch" }} />
        {/* Trend */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 28 }}>
          <span style={{ fontSize: 14, fontWeight: 800, color: trendColor, lineHeight: 1 }}>{trendArrow}</span>
          <span style={{ fontSize: 11, color: "#829aae", letterSpacing: 0.5 }}>TREND</span>
        </div>
        <div style={{ width: 1, background: "#0d2035", alignSelf: "stretch" }} />
        {/* 15 min count */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 28 }}>
          <span style={{ fontSize: 14, fontWeight: 800, color: burstStats.last15 > 10 ? "#f0883e" : "#c0d0e0", lineHeight: 1 }}>{burstStats.last15}</span>
          <span style={{ fontSize: 11, color: "#829aae", letterSpacing: 0.5 }}>15 MIN</span>
        </div>
        <div style={{ flex: 1 }} />
        {/* Network breakdown pills */}
        <div title="Up to three largest source categories across all loaded reports, before time-window and feed filters" style={{ display: "flex", flexDirection:"column", alignItems:"flex-end", gap: 3 }}>
          <span style={{fontSize:9,color:"#829aae",letterSpacing:0.5}}>ALL LOADED</span>
          <div style={{display:"flex",gap:4}}>
          {Object.entries(burstStats.nets).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([net, count]) => (
            <span key={net} style={{
              fontSize: 11, padding: "1px 5px", borderRadius: 3, fontWeight: 700,
              background: net === "TG" ? "rgba(77,171,247,0.12)" : net === "𝕏" ? "rgba(200,200,200,0.08)" : "rgba(245,158,11,0.12)",
              color: net === "TG" ? "#4dabf7" : net === "𝕏" ? "#9ca3af" : "#f59e0b",
              border: `1px solid ${net === "TG" ? "rgba(77,171,247,0.25)" : net === "𝕏" ? "rgba(200,200,200,0.15)" : "rgba(245,158,11,0.25)"}`,
            }}>
              {net}&nbsp;{count}
            </span>
          ))}
          </div>
        </div>
      </div>

      {/* ── FILTER PANEL (collapsible) ────────────────────────────────────── */}
      {filtersOpen && (
        <div className="report-filter-panel" role="region" aria-label="Report filters" tabIndex={0} style={{
          padding: "8px 12px",
          borderBottom: "1px solid #0a1a2a",
          background: "#040d1a",
          display: "flex", flexDirection: "column", gap: 6,
          flexShrink: 0,
        }}>
          {/* Search */}
          <input
            type="text"
            placeholder="Search events, locations, sources…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              background: "#060e1a", border: "1px solid #0d2035", borderRadius: 4,
              color: "#c0d8f0", fontSize: 11, padding: "5px 9px",
              fontFamily: "var(--font-mono)", outline: "none", width: "100%", boxSizing: "border-box",
            }}
          />
          {/* Type filter chips */}
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {Object.entries(TYPE_COLORS).map(([type, color]) => (
              <button
                key={type}
                aria-pressed={typeFilter===type}
                onClick={() => setTypeFilter(typeFilter === type ? null : type)}
                style={{
                  background: typeFilter === type ? `${color}20` : "transparent",
                  border: `1px solid ${typeFilter === type ? `${color}88` : "#0d2035"}`,
                  color: typeFilter === type ? color : "#8da3b7",
                  fontSize: 11, padding: "2px 7px", borderRadius: 3, cursor: "pointer",
                  fontFamily: "var(--font-mono)", fontWeight: 700, letterSpacing: 0.3,
                  transition: "all 0.15s",
                }}
              >
                {TYPE_ICONS[type]} {type.replace("_", " ").toUpperCase()}
              </button>
            ))}
          </div>
          {/* Row 2: severity, source, sort, confirmed */}
          <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            {/* Min severity */}
            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ fontSize: 11, color: "#8da3b7", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>SEV≥</span>
              {[1, 3, 5, 7, 9].map((v) => (
                <button
                  key={v}
                  title={v === 1 ? "All severities, including unscored" : `Scored severity ${v}/10 and above`}
                  aria-label={v === 1 ? "All severities, including unscored" : `Scored severity ${v}/10 and above`}
                  aria-pressed={minSev === v}
                  onClick={() => setMinSev(minSev === v ? 1 : v)}
                  style={{
                    background: minSev === v ? `${sevColor(v)}20` : "transparent",
                    border: `1px solid ${minSev === v ? `${sevColor(v)}66` : "#0d2035"}`,
                    color: minSev === v ? sevColor(v) : "#8da3b7",
                    fontSize: 11, padding: "2px 5px", borderRadius: 3, cursor: "pointer",
                    fontFamily: "var(--font-mono)", fontWeight: 700,
                  }}
                >{v === 1 ? "ALL" : v}</button>
              ))}
            </div>
            <div style={{ width: 1, background: "#0d2035", height: 14 }} />
            {/* Source filter */}
            {["TG", "𝕏", "RSS", "SENSOR", "OTHER"].map((src) => {
              const key = src === "TG" ? "telegram" : src === "𝕏" ? "x" : src==="SENSOR" ? "sensor" : src==="OTHER"?"other":"rss";
              return (
                <button
                  key={src}
                  aria-pressed={sourceFilter===key}
                  onClick={() => setSourceFilter(sourceFilter === key ? null : key)}
                  style={{
                    background: sourceFilter === key ? "rgba(88,166,255,0.12)" : "transparent",
                    border: `1px solid ${sourceFilter === key ? "rgba(88,166,255,0.4)" : "#0d2035"}`,
                    color: sourceFilter === key ? "#58a6ff" : "#8da3b7",
                    fontSize: 11, padding: "2px 6px", borderRadius: 3, cursor: "pointer",
                    fontFamily: "var(--font-mono)", fontWeight: 700,
                  }}
                >{src}</button>
              );
            })}
            <div style={{ width: 1, background: "#0d2035", height: 14 }} />
            {/* Sort */}
            {(["new", "sev", "conf"] as const).map((m) => (
              <button
                key={m}
                aria-pressed={sortMode===m}
                onClick={() => setSortMode(m)}
                style={{
                  background: sortMode === m ? "rgba(88,166,255,0.12)" : "transparent",
                  border: `1px solid ${sortMode === m ? "rgba(88,166,255,0.4)" : "#0d2035"}`,
                  color: sortMode === m ? "#58a6ff" : "#8da3b7",
                  fontSize: 11, padding: "2px 6px", borderRadius: 3, cursor: "pointer",
                  fontFamily: "var(--font-mono)", fontWeight: 700, letterSpacing: 0.3,
                }}
              >{m === "new" ? "NEWEST" : m === "sev" ? "SEVERITY" : "MULTI-REPORT"}</button>
            ))}
            <div style={{ flex: 1 }} />
            {/* Confirmed only toggle */}
            <button
              aria-pressed={confirmedOnly}
              onClick={() => setConfirmedOnly(v => !v)}
              style={{
                background: confirmedOnly ? "rgba(63,185,80,0.12)" : "transparent",
                border: `1px solid ${confirmedOnly ? "rgba(63,185,80,0.4)" : "#0d2035"}`,
                color: confirmedOnly ? "#3fb950" : "#8da3b7",
                fontSize: 11, padding: "2px 7px", borderRadius: 3, cursor: "pointer",
                fontFamily: "var(--font-mono)", fontWeight: 700,
              }}
            >✓ MULTI-REPORT ONLY</button>
            {activeFilterCount > 0 && (
              <button
                onClick={() => { setSearch(""); setMinSev(1); setTypeFilter(null); setSourceFilter(null); setConfirmedOnly(false); setSortMode("new"); }}
                style={{
                  background: "rgba(248,81,73,0.08)", border: "1px solid rgba(248,81,73,0.3)",
                  color: "#f85149", fontSize: 11, padding: "2px 7px", borderRadius: 3,
                  cursor: "pointer", fontFamily: "var(--font-mono)", fontWeight: 700,
                }}
              >✕ CLEAR</button>
            )}
          </div>
        </div>
      )}

      {/* ── EVENT STREAM ─────────────────────────────────────────────────── */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        role="region" aria-label="Report feed entries" tabIndex={0}
        style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}
      >
        {filteredEvents.length === 0 && (
          <div style={{ padding: 32, textAlign: "center", color: "#1e3a5a", fontSize: 12, fontFamily: "var(--font-mono)", letterSpacing: 1 }}>
            <div style={{ fontSize: 28, marginBottom: 10, opacity: 0.3 }}>◎</div>
            {activeFilterCount>0 ? "No reports match active filters" : "No reports in this window"}
          </div>
        )}

        {filteredEvents.slice(0, 600).map((evt, idx) => {
          const isNew      = newIds.has(evt.id);
          const isCrit     = (evt.severity ?? 0) >= 9;
          const ageMs      = nowMs() - new Date(evt.timestamp).getTime();
          const isRecent   = Number.isFinite(ageMs)&&ageMs>=0&&ageMs < 5 * 60000;
          const hasPin     = hasUsableReportCoordinates(evt);
          const hasSrcUrl  = !!safeUrl(evt.source_url);
          const cm         = chanMeta(evt.channel_name || evt.source || "");
          const typeColor  = TYPE_COLORS[evt.event_type] ?? "#a3b9ca";
          const sColor     = sevColor(evt.severity ?? 1);

          return (
            <div
              key={evt.id}
              className={`intel-card${selectedEventId===evt.id ? " intel-card-selected" : ""}${isNew ? " intel-card-new" : ""}${isCrit ? " intel-card-crit" : ""}`}
              onClick={(event) => {if((event.target as HTMLElement).closest("button,a,details")) return;if(hasPin)onEventClick?.(evt);}}
              style={{
                padding: "10px 12px 8px 14px",
                borderLeft: `3px solid ${isRecent ? typeColor : typeColor + "88"}`,
                background: isNew
                  ? "rgba(63,185,80,0.06)"
                  : isCrit
                  ? "rgba(248,81,73,0.04)"
                  : isRecent
                  ? "rgba(255,255,255,0.015)"
                  : "transparent",
                borderBottom: "1px solid rgba(255,255,255,0.025)",
                cursor: hasPin ? "pointer" : "default",
                animationDelay: `${idx * 15}ms`,
                position: "relative",
              }}
            >
              {/* ── Row 1: Age / badges / severity ─────────────────────── */}
              <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 5, flexWrap: "wrap" }}>
                <AgeChip timestamp={evt.timestamp} />
                {/* Type badge */}
                <span style={{
                  fontSize: 11, padding: "1px 5px", borderRadius: 2,
                  background: `${typeColor}18`, color: typeColor,
                  fontWeight: 700, fontFamily: "var(--font-mono)", border: `1px solid ${typeColor}33`,
                  letterSpacing: 0.3,
                }}>
                  {TYPE_ICONS[evt.event_type]} {(evt.event_type ?? "UNK").replace("_", " ").toUpperCase()}
                </span>
                {/* Confirmation */}
                <ConfBadge evt={evt} />
                <div style={{ flex: 1 }} />
                {/* Severity pill */}
                <span style={{
                  fontSize: 11, fontWeight: 800, padding: "1px 6px", borderRadius: 3,
                  background: (evt.severity ?? 0) >= 8 ? sColor : "transparent",
                  color: (evt.severity ?? 0) >= 8 ? "#06101a" : sColor,
                  border: (evt.severity ?? 0) >= 8 ? "none" : `1px solid ${sColor}55`,
                  fontFamily: "var(--font-mono)", lineHeight: 1.4,
                }}>
                  {severityLabel(evt)}
                </span>
              </div>

              {/* ── Row 2: Summary ──────────────────────────────────────── */}
              <div style={{
                fontSize: 12, lineHeight: 1.5, color: isRecent ? "#dce8f5" : "#a8bdd0",
                fontWeight: isRecent ? 500 : 400,
                marginBottom: 6,
              }}>
                {evt.summary || evt.raw_text?.slice(0, 160) || "—"}
              </div>

              {/* ── Row 3: Meta row ─────────────────────────────────────── */}
              <div style={{
                display: "flex", alignItems: "center", gap: 6,
                fontSize: 11, fontFamily: "var(--font-mono)", color: "#8da3b7",
                flexWrap: "wrap",
              }}>
                {/* Source */}
                <span title={cm.tip} style={{ display: "flex", alignItems: "center", gap: 4, cursor: "help", color: "#8ea8be" }}>
                  <span>{cm.flag}</span>
                  <span style={{ color: relColor(evt.source_reliability) }}>{cm.label}</span>
                  <QualityDots score={evt.source_reliability} />
                </span>

                <span title="Source time can represent publication, an update or sensor acquisition; incident time is unverified" style={{color:"#9aafbd"}}>Source time</span>
                {!hasPin && <span style={{color:"#a9b6c4"}}>Location unresolved</span>}
                {/* Location */}
                {evt.location_name && evt.location_name.toLowerCase() !== "unknown" && (
                  <span style={{ color: "#8fb7d7", display: "flex", alignItems: "center", gap: 3 }}>
                    <span style={{ opacity: 0.6 }}>📍</span>
                    <span>{evt.location_name}</span>
                  </span>
                )}

                <div style={{ flex: 1 }} />

                {/* Action buttons */}
                {hasPin && onEventClick && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onEventClick(evt); }}
                    style={{
                      background: "rgba(88,166,255,0.08)", border: "1px solid rgba(88,166,255,0.25)",
                      color: "#8fb7d7", borderRadius: 3, padding: "1px 7px", fontSize: 11,
                      cursor: "pointer", fontFamily: "var(--font-mono)", fontWeight: 600,
                      letterSpacing: 0.3,
                    }}
                    aria-label={`Locate report: ${evt.location_name || evt.summary}`}
                  >↗ LOCATE</button>
                )}
                {hasSrcUrl && (
                  <a
                    href={safeUrl(evt.source_url)}
                    target="_blank" rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    style={{
                      background: "rgba(63,185,80,0.08)", border: "1px solid rgba(63,185,80,0.25)",
                      color: "#94d5b1", borderRadius: 3, padding: "1px 7px", fontSize: 11,
                      textDecoration: "none", fontFamily: "var(--font-mono)", fontWeight: 600,
                      letterSpacing: 0.3,
                    }}
                  >
                    {evt.source_url!.includes("t.me") ? "↗ TG" : evt.source_url!.includes("x.com") || evt.source_url!.includes("twitter") ? "↗ 𝕏" : "↗ SRC"}
                  </a>
                )}
              </div>

              <EvidenceDetails event={evt} />

              {/* ── Severity bar at bottom ─────────────────────────────── */}
              <div style={{ height: 2, background: "#050e1a", borderRadius: 1, marginTop: 7 }}>
                <div style={{
                  height: "100%", borderRadius: 1,
                  width: `${((evt.severity ?? 1) / 10) * 100}%`,
                  background: `linear-gradient(to right, #1a3a6a, ${typeColor})`,
                  transition: "width 0.4s ease",
                }} />
              </div>
            </div>
          );
        })}

        {/* Bottom padding */}
        <div style={{ height: 20 }} />
      </div>

      {/* ── SCROLL TO TOP ────────────────────────────────────────────────── */}
      {!autoScroll && (
        <button
          onClick={() => {
            if (containerRef.current) containerRef.current.scrollTop = 0;
            setAutoScroll(true);
          }}
          style={{
            position: "absolute", bottom: 14, left: "50%", transform: "translateX(-50%)",
            background: "rgba(3,12,24,0.95)", border: "1px solid #1a3a5a",
            color: "#58a6ff", fontSize: 11, padding: "5px 14px", borderRadius: 20,
            cursor: "pointer", fontFamily: "var(--font-mono)", fontWeight: 700,
            letterSpacing: 0.5, zIndex: 10, backdropFilter: "blur(4px)",
            boxShadow: "0 2px 12px rgba(0,0,0,0.5)",
          }}
        >↑ LATEST</button>
      )}
    </div>
  );
}
