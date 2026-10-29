import {isSourceDigest} from "../lib/brief";
import { nowMs } from "../lib/clock";
import { MediaFrame, ShowcaseBriefing } from "./MediaFrame";
import { SHOWCASE, safeUrl } from "../lib/runtime";
import {isScored,severityLabel} from "../lib/events";
import {recentReports,sourceFamilyCounts,sourceAge} from "../lib/reportPresentation";
import { apiFetch } from "../lib/api";
import { API_BASE } from "../lib/runtime";
import { MEDIA_BASE } from "../lib/runtime";
/**
 * IntelMediaView — MEDIA / INTEL dashboard tab  (v4 — 2×2 broadcast grid)
 *
 * v4 changes:
 *  - 2×2 cam grid: TriggerSmart Radio | SITREP Video | Prof. Jiang | Intel Cams Live
 *  - SITREP text panel removed (replaced by SITREP broadcast video cell)
 *  - Intel panels now full-width in row 2
 *  - SitrepVideoCell: HTML5 video player with live metadata overlay
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import type { ConflictEvent } from "../types/event";


const VIDEO_BASE = MEDIA_BASE;

// ─── Predictive History / Prof. Jiang recorded reference IDs (not a latest-video feed) (GT# descending) ───────
const JIANG_VIDEOS = [
  { ep: 16, id: "mk4vcHtawSo", title: "Pax Judaica Rising",        law: "PAX JUDAICA RISING" },
  { ep: 15, id: "TQs3rRnOEbc", title: "The Return of History",     law: "RETURN OF HISTORY" },
  { ep: 14, id: "yXz9CqFkFh0", title: "The Law of Proximity",      law: "LAW OF PROXIMITY" },
  { ep: 13, id: "aCJL3hH3OTQ", title: "Epstein's World",           law: "EPSTEIN NETWORKS" },
  { ep: 12, id: "K8ZmFl53nTs", title: "Eschatological Convergence",law: "ESC. CONVERGENCE" },
];

type IntelPanelType = "breaking" | "sources" | "threats" | "radiation";

// ─── Escalation colors ─────────────────────────────────────────────────────────
const LEVEL_COLORS: Record<string, string> = {
  STABLE:     "#3fb950",
  ELEVATED:   "#d29922",
  ESCALATING: "#f0883e",
  CRITICAL:   "#f85149",
};

// ─── Vessel types removed (replaced by SourceIntelPanel) ───

// ─── CamCell wrapper ──────────────────────────────────────────────────────────
function CamCell({
  label, sublabel, color = "#58a6ff", gradientPos = "bottom", badge, children
}: {
  label: string; sublabel?: string; color?: string; gradientPos?: "top"|"bottom";
  badge?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="media-source-cell" style={{ border: `1px solid ${color}22`, flexDirection: gradientPos === "bottom" ? "column-reverse" : "column" }}>
      <div className="media-source-caption">
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: color, flexShrink: 0,
            animation: "statusPulse 2s ease-in-out infinite", boxShadow: `0 0 5px ${color}` }} />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
            color, letterSpacing: 1.2 }}>{label}</span>
          {badge}
        </div>
        {sublabel && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#8ea8be", marginTop: 1 }}>
            {sublabel}
          </div>
        )}
      </div>
      <div className="media-source-content">{children}</div>
    </div>
  );
}

// ─── Multi-Source Conflict Feed Cell ─────────────────────────────────────────
const CONFLICT_FEEDS = [
  {
    ch: "mezmorised",
    tag: "CAMS",
    label: "CONFLICT CAMS — CCTV GRID",
    sub: "External camera aggregator · current stream/location unverified",
    col: "#888888",
  },
  {
    ch: "texasnewsstudiotv",
    tag: "AGG",
    label: "MULTI-SOURCE AGGREGATOR",
    sub: "External conflict coverage · current stream availability unverified",
    col: "#f0883e",
  },
  {
    ch: "agendafreetv",
    tag: "WEST",
    label: "WAR COVERAGE — WESTERN",
    sub: "External coverage/camera player · acquisition time unverified",
    col: "#6699ff",
  },
  {
    ch: "theredbearddude",
    tag: "IL",
    label: "SAFETY STREAM — IL FOCUSED",
    sub: "External defense-focused commentary · claims require verification",
    col: "#ff9b91",
  },
] as const;

function ConflictFeedCell() {
  const [idx, setIdx] = useState(0);
  const f = CONFLICT_FEEDS[idx];
  return (
    <CamCell label={f.label} sublabel={f.sub} color={f.col} gradientPos="top">
      <div className="conflict-feed-content"><div className="conflict-feed-player">
      <MediaFrame
        key={f.ch}
        src={`https://player.twitch.tv/?channel=${f.ch}&parent=${encodeURIComponent(window.location.hostname)}&autoplay=true&muted=true`}
        style={{ width: "100%", height: "100%", border: "none" }}
        allow="autoplay; encrypted-media"
        allowFullScreen
        loading="lazy"
        title={f.label}
      />
      </div>
      <div className="conflict-feed-selector" role="group" aria-label="Camera source">
        {CONFLICT_FEEDS.map((src, i) => (
          <button
            key={src.ch}
            onClick={() => setIdx(i)}
            style={{
              padding: "2px 7px",
              fontSize: 11,
              fontFamily: "var(--font-mono)",
              background: i === idx ? src.col : "rgba(3,5,8,0.88)",
              color: i === idx ? "#000" : src.col,
              border: `1px solid ${i === idx ? src.col : src.col + "55"}`,
              cursor: "pointer",
              borderRadius: 2,
              fontWeight: 700,
              letterSpacing: 0.8,
              transition: "all 0.15s",
            }}
          >
            {src.tag}
          </button>
        ))}
      </div></div>
    </CamCell>
  );
}

// ─── SITREP Broadcast Video Cell ───────────────────────────────────────────────
function LiveSitrepVideoCell() {
  const [videoKey, setVideoKey] = useState(nowMs());
  const [sitrep, setSitrep] = useState<{
    id:number; escalation_level: string; headline: string; generated_at: string; events_analyzed: number; trigger?:string; analysis_status?:string;
  } | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoUrl,setVideoUrl]=useState<string|null>(null);
  const [briefState,setBriefState]=useState<"loading"|"ready"|"empty"|"unavailable">("loading");

  // Refresh video URL every 5 min
  useEffect(() => {
    const t = setInterval(() => setVideoKey(nowMs()), 5 * 60 * 1000);
    return () => clearInterval(t);
  }, []);

  // Fetch SITREP metadata
  useEffect(() => {
    const load = async () => {
      try {
        const r = await apiFetch(`${API_BASE}/sitreps/latest`);
        const j = await r.json();
        if(!r.ok)throw new Error("Brief unavailable");
        setSitrep(j.sitrep||null);setBriefState(j.sitrep?"ready":"empty");
        setVideoUrl(null);
      } catch {setBriefState("unavailable");}
    };
    load();
    const t = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(()=>{
    let cancelled=false;
    if(!sitrep||isSourceDigest(sitrep))return;
    void apiFetch(`${API_BASE}/config`).then(r=>r.json()).then(async config=>{
      if(!config.video_generation_enabled)return;
      const response=await apiFetch(`${VIDEO_BASE}/videos/manifest.json`);
      if(!response.ok)return;
      const manifest=await response.json();const item=manifest[String((sitrep as any).id)];
      if(!cancelled&&typeof item?.url==="string"&&item.url.startsWith("/videos/"))setVideoUrl(item.url);
    }).catch(()=>{});
    return()=>{cancelled=true;};
  },[sitrep]);
  const levelColor = sitrep ? (LEVEL_COLORS[sitrep.escalation_level] || "#91c9e8") : "#58a6ff";
  const videoSrc=videoUrl ? `${VIDEO_BASE}${videoUrl}?t=${videoKey}` : null;



  return (
    <div style={{ position: "relative", background: "#000", overflow: "hidden",
      border: `1px solid ${levelColor}55`, display: "flex", flexDirection: "column" }}>

      {/* Header bar */}
      <div style={{
        padding: "5px 8px", flexShrink: 0,
        background: `linear-gradient(90deg, ${levelColor}18 0%, rgba(3,5,8,0.95) 100%)`,
        borderBottom: `1px solid ${levelColor}33`,
        display: "flex", alignItems: "center", gap: 7,
      }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: levelColor, flexShrink: 0,
          animation: "statusPulse 1.5s ease-in-out infinite", boxShadow: `0 0 6px ${levelColor}` }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 800,
          letterSpacing: 1.8, color: levelColor }}>{isSourceDigest(sitrep)?"▤ SOURCE BRIEFING":"◈ SITUATION BRIEF"}</span>
        {sitrep && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
            color: levelColor, background: `${levelColor}22`, padding: "1px 6px", borderRadius: 2,
            letterSpacing: 1 }}>{sitrep.escalation_level}</span>
        )}
        {sitrep && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#8da3b7", marginLeft: "auto" }}>
            {sourceAge(sitrep.generated_at,nowMs())} · {sitrep.events_analyzed} REPORTS
          </span>
        )}
      </div>

      {briefState==="unavailable"&&<p role="status">Briefing service unavailable · any retained summary may be stale</p>}
      {/* Video player */}
      <div style={{ flex: 1, position: "relative", background: "#000" }}>
        {videoSrc?<video ref={videoRef} key={videoKey} controls preload="metadata" style={{width:"100%",height:"100%",objectFit:"contain"}}><source src={videoSrc} type="video/mp4"/></video>:<div className="media-empty-state"><span>TEXT SOURCE BRIEFING</span><h2>{sitrep?.headline||(briefState==="unavailable"?"Briefing service unavailable":briefState==="loading"?"Loading source briefing…":"No source briefing yet")}</h2><p>{isSourceDigest(sitrep)?"An attributed compilation of collected reports is available in Brief. No model inference, recorded narration or video is implied.":"Open Brief to inspect collected sources and available analysis. No video is configured for this report."}</p></div>}
      </div>

      {/* Headline ticker at bottom */}
      {sitrep && (
        <div style={{
          padding: "3px 8px", flexShrink: 0,
          background: "rgba(3,5,8,0.97)", borderTop: `1px solid ${levelColor}22`,
          fontFamily: "var(--font-mono)", fontSize: 11, color: "#6a8a9a",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          <span style={{ color: levelColor, marginRight: 5 }}>◈</span>{sitrep.headline}
        </div>
      )}
    </div>
  );
}

// ─── Breaking Intel Panel (replaces EAM) ─────────────────────────────────────
function BreakingIntelPanel({ events,clock }: { events: ConflictEvent[];clock:number }) {
  const recent=useMemo(()=>recentReports(events,clock,4),[events,clock]),top=recent.slice(0,8);
  const age=(timestamp:string)=>sourceAge(timestamp,clock);
  const srcShort = (src: string) =>
    (src || "").replace("rss_x_", "@").replace("rss_", "").replace(/_/g, ".").toUpperCase().slice(0, 18);

  return (
    <div style={{ padding: "6px 10px", height: "100%", display: "flex", flexDirection: "column", gap: 3, overflow: "hidden" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
        borderBottom: "1px solid rgba(248,81,73,0.2)", paddingBottom: 5, flexShrink: 0 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
          letterSpacing: 1.5, color: "#f85149" }}>RECENT SOURCE REPORTS — LAST 4H</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#8b9eaf" }}>
          {top.length} / {recent.length} LOADED REPORTS
        </span>
      </div>
      <div style={{ flex: 1, overflow: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
        {top.length === 0 && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#829aae",
            textAlign: "center", marginTop: 12 }}>No loaded reports with source timestamps in the last 4h</div>
        )}
        {top.map(evt => {
          const sev = evt.severity || 0;
          const sc = !isScored(evt)?"#a3b9ca":sev >= 8 ? "#f85149" : sev >= 6 ? "#f0883e" : "#d29922";
          const url=safeUrl(evt.source_url);const hasUrl=!!url;
          return (
            <a key={evt.id}
              href={url||undefined}
              target={hasUrl ? "_blank" : "_self"}
              rel="noopener noreferrer"
              style={{ display: "grid", gridTemplateColumns: "62px 1fr 28px",
                gap: 5, padding: "4px 5px", borderRadius: 2, textDecoration: "none",
                background: sev >= 8 ? "rgba(248,81,73,0.05)" : "rgba(10,14,20,0.5)",
                border: `1px solid ${sev >= 8 ? "rgba(248,81,73,0.2)" : "rgba(20,30,45,0.6)"}`,
                cursor: hasUrl ? "pointer" : "default", transition: "background 0.12s",
              }}
              onMouseEnter={e => hasUrl && ((e.currentTarget as HTMLElement).style.background = `${sc}12`)}
              onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background =
                sev >= 8 ? "rgba(248,81,73,0.05)" : "rgba(10,14,20,0.5)")}
            >
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center",
                justifyContent: "center", gap: 2 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 800,
                  color: sc }}>{severityLabel(evt)}</span>

              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#c9d1d9",
                  lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis",
                  display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as any }}>
                  {evt.summary}
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#8da3b7", marginTop: 1 }}>
                  {srcShort(evt.source || "")}
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end",
                justifyContent: "space-between" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11,
                  color: "#a3b9ca" }}>{age(evt.timestamp)}</span>
                {hasUrl && <span style={{ fontFamily: "var(--font-mono)", fontSize: 11,
                  color: "#8da3b7" }}>↗</span>}
              </div>
            </a>
          );
        })}
      </div>
    </div>
  );
}

// ─── Source Intelligence Panel (replaces Vessel Risk) ─────────────────────────
function SourceIntelPanel({ events,clock }: { events: ConflictEvent[];clock:number }) {
  const stats = useMemo(() => {
    const h6=recentReports(events,clock,6);
    // Group by source channel
    const counts: Record<string, number> = {};
    h6.forEach(e => {
      const src = (e.source || "unknown").toLowerCase();
      counts[src] = (counts[src] || 0) + 1;
    });
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 8);
    return {sorted,...sourceFamilyCounts(h6),total:h6.length};
  }, [events,clock]);

  const label = (src: string) => {
    if (src === "telegram") return "TELEGRAM";
    if (src.startsWith("rss_x_")) return src.replace("rss_x_", "@").toUpperCase();
    return src.replace("rss_", "").replace(/_/g, " ").toUpperCase();
  };
  const color = (src: string) => {
    if (src === "telegram") return "#58a6ff";
    if (src.startsWith("rss_x_")) return "#e6edf3";
    return "#d29922";
  };

  return (
    <div style={{ padding: "8px 12px", height: "100%", display: "flex", flexDirection: "column", gap: 5, overflow: "hidden" }}>
      <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid rgba(240,136,62,0.2)", paddingBottom: 5, flexShrink: 0 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: 1.5, color: "#f0883e" }}>◈ SOURCE RECORDS — LAST 6H</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#8b9eaf" }}>{stats.total} REPORTS</span>
      </div>
      <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
        {[{ l: "TG", v: stats.telegram, c: "#58a6ff" }, { l: "X", v: stats.x, c: "#e6edf3" }, { l: "RSS", v: stats.rss, c: "#d29922" }, {l:"SENSOR",v:stats.sensor,c:"#91c9e8"}, {l:"OTHER",v:stats.other,c:"#a3b9ca"}].map(s => (
          <div key={s.l} style={{ flex: 1, background: "rgba(10,14,20,0.6)", borderRadius: 3, padding: "4px", textAlign: "center", border: `1px solid ${s.c}22` }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: s.c }}>{s.v}</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#8da3b7" }}>{s.l}</div>
          </div>
        ))}
      </div>
      <div role="region" aria-label="Source record counts" tabIndex={0} style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
        {stats.sorted.map(([src, count]) => (
          <div key={src} style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 4px", borderRadius: 2,
            background: "rgba(10,14,20,0.4)", border: "1px solid rgba(30,40,55,0.4)" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: color(src),
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label(src)}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
              <div style={{ width: Math.max(20, Math.min(80, (count / Math.max(...stats.sorted.map(([,v])=>v))) * 80)), height: 3,
                background: color(src), borderRadius: 2, opacity: 0.6 }} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: color(src), width: 20, textAlign: "right" }}>{count}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Threat Matrix Panel (replaces Activity Index) ────────────────────────────
function ThreatMatrixPanel({ events,clock }: { events: ConflictEvent[];clock:number }) {
  const stats = useMemo(() => {
    const h24=recentReports(events,clock,24);
    const byType: Record<string, number> = {};
    h24.forEach(e => {
      const t = (e.event_type || "other").toLowerCase();
      byType[t] = (byType[t] || 0) + 1;
    });
    const conf = h24.filter(e => (e.evidence?.unique_source_count??1)>1).length;
    const sorted = Object.entries(byType).sort((a, b) => b[1] - a[1]).slice(0, 6);
    return { sorted,scored:h24.filter(isScored).length,conf, unscored:h24.filter(e=>!isScored(e)).length,total: h24.length };
  }, [events,clock]);

  const typeColor: Record<string, string> = {
    military: "#f85149", strike: "#f85149", airstrike: "#f85149",
    economic: "#d29922", political: "#bc8cff",
    humanitarian: "#3fb950", diplomatic: "#58a6ff",
  };

  return (
    <div style={{ padding: "8px 12px", height: "100%", display: "flex", flexDirection: "column", gap: 5, overflow: "hidden" }}>
      <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid rgba(165,214,255,0.15)", paddingBottom: 5, flexShrink: 0 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: 1.5, color: "#a5d6ff" }}>REPORT MIX — SOURCE CLOCK 24H</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#8b9eaf" }}>{stats.total} REPORTS</span>
      </div>
      <p style={{margin:0,fontSize:10,color:"#a3b9ca"}}>Stored scores are unreviewed. Multiple source records may share one origin.</p>
      <div style={{ display: "flex", gap: 5, flexShrink: 0 }}>
        {[{l:"SCORED",v:stats.scored,c:"#91c9e8"},{l:"UNSCORED",v:stats.unscored,c:"#a3b9ca"},{l:"MULTI-RECORD",v:stats.conf,c:"#91c9e8"}].map(s => (
          <div key={s.l} style={{ flex: 1, background: "rgba(10,14,20,0.6)", borderRadius: 3, padding: "4px", textAlign: "center", border: `1px solid ${s.c}22` }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: s.c }}>{s.v}</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#8da3b7" }}>{s.l}</div>
          </div>
        ))}
      </div>
      <div role="region" aria-label="Report type counts" tabIndex={0} style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
        {stats.sorted.map(([type, count]) => {
          const c = typeColor[type] || "#a3b9ca";
          const pct = stats.total > 0 ? Math.round((count / stats.total) * 100) : 0;
          return (
            <div key={type} style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 4px",
              borderRadius: 2, background: "rgba(10,14,20,0.4)", border: `1px solid ${c}18` }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: c,
                width: 80, textTransform: "uppercase", flexShrink: 0 }}>{type.slice(0, 10)}</span>
              <div style={{ flex: 1, height: 3, background: "#0d1a26", borderRadius: 2 }}>
                <div style={{ width: `${pct}%`, height: "100%", background: c, borderRadius: 2, opacity: 0.75 }} />
              </div>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: c, width: 28, textAlign: "right", flexShrink: 0 }}>{count}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SitrepVideoCell() { return SHOWCASE ? <ShowcaseBriefing /> : <LiveSitrepVideoCell />; }

// ─── Main Component ────────────────────────────────────────────────────────────
export function IntelMediaView({ events }: { events: ConflictEvent[] }) {
  const [clock,setClock]=useState(nowMs);
  useEffect(()=>{const timer=setInterval(()=>setClock(nowMs()),30000);return()=>clearInterval(timer);},[]);
  const [activePanel, setActivePanel] = useState<IntelPanelType>("breaking");
  const [panelCycling, setPanelCycling] = useState(!SHOWCASE);
  const cycleTimer = useRef<ReturnType<typeof setInterval>>(undefined);
  const panelOrder: IntelPanelType[] = ["breaking", "sources", "threats", "radiation"];

  // Source references have separate empty and failed states; a failure never refreshes their clock.
  const [sitrepEvents, setSitrepEvents] = useState<ConflictEvent[]>([]);
  const [sitrepMeta, setSitrepMeta] = useState<any>(null);
  const [sourceStatus,setSourceStatus]=useState<"loading"|"ready"|"empty"|"unavailable">("loading");
  useEffect(() => {
    const controller=new AbortController();let cancelled=false;
    const load=async()=>{
      try{
        const r=await apiFetch(`${API_BASE}/sitreps/latest`,{signal:controller.signal});if(!r.ok)throw Error();const j=await r.json();
        if(!j.sitrep?.id){if(!cancelled){setSitrepMeta(null);setSitrepEvents([]);setSourceStatus("empty");}return;}
        const er=await apiFetch(`${API_BASE}/sitreps/${j.sitrep.id}/events`,{signal:controller.signal});if(!er.ok)throw Error();const ej=await er.json();const rows=Array.isArray(ej)?ej:ej.events;
        if(!Array.isArray(rows))throw Error();if(!cancelled){setSitrepMeta(j.sitrep);setSitrepEvents(rows);setSourceStatus(rows.length?"ready":"empty");}
      }catch{if(!cancelled)setSourceStatus("unavailable");}
    };
    void load();const timer=setInterval(()=>void load(),5*60000);return()=>{cancelled=true;controller.abort();clearInterval(timer);};
  }, []);

  useEffect(() => {
    clearInterval(cycleTimer.current);
    if (!panelCycling) return;
    cycleTimer.current = setInterval(() => {
      setActivePanel(p => panelOrder[(panelOrder.indexOf(p) + 1) % panelOrder.length]);
    }, 25000);
    return () => clearInterval(cycleTimer.current);
  }, [panelCycling]);

  const PANEL_META: Record<IntelPanelType, { label: string; icon: string; color: string }> = {
    breaking:  { label: "RECENT REPORTS",  icon: "⚡", color: "#f85149" },
    sources:   { label: "SOURCE RECORDS",    icon: "◈", color: "#f0883e" },
    threats:   { label: "REPORT MIX",   icon: "⚡", color: "#a5d6ff" },
    radiation: { label: "RADIATION",       icon: "☢", color: "#3fb950" },
  };



  return (
    <div className="media-desk" style={{
      width: "100%",
      height: "100%",
      minHeight:640,
      display: "grid",
      gridTemplateRows: "minmax(380px,1fr) 148px 112px",
      background: "#030508",
      overflow: "hidden",
    }}>

      {/* ── ROW 1: 2×2 Broadcast Grid ──────────────────────────────────────── */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gridTemplateRows: "minmax(0, 1fr) minmax(0, 1fr)",
        gap: "1px",
        background: "rgba(15,22,35,0.6)",
        overflow: "hidden",
        borderBottom: "1px solid rgba(25,35,50,0.8)",
      }}>

        {/* [0,0] Al Jazeera English — Live 24/7 */}
        <CamCell
          label="AL JAZEERA ENGLISH"
          sublabel="External broadcast player · current playback availability unverified"
          color="#ff9500"
        >
          <MediaFrame
            src="https://players.brightcove.net/665003303001/AvByVmBYDu_default/index.html?videoId=6368602483112&autoplay=true"
            style={{ width: "100%", height: "100%", border: "none" }}
            allow="autoplay; encrypted-media; picture-in-picture"
            allowFullScreen
            title="Al Jazeera English Live"
          />
        </CamCell>

        {/* [0,1] SITREP Video Player */}
        <SitrepVideoCell />

        {/* [1,0] Prof. Jiang — Predictive History */}
        <CamCell
          label={`PREDICTIVE HISTORY — GT#${JIANG_VIDEOS[0].ep}`}
          sublabel={`Recorded analytical reference · publication date unverified · ${JIANG_VIDEOS[0].law}`}
          color="#bc8cff"
          gradientPos="top"
        >
          <MediaFrame
            src={`https://www.youtube-nocookie.com/embed/${JIANG_VIDEOS[0].id}?modestbranding=1&rel=0&color=white`}
            style={{ width: "100%", height: "100%", border: "none" }}
            allow="autoplay; encrypted-media; picture-in-picture"
            allowFullScreen
            loading="lazy"
            title={`Predictive History GT#${JIANG_VIDEOS[0].ep}: ${JIANG_VIDEOS[0].law}`}
          />
        </CamCell>

        {/* [1,1] Multi-source conflict feed — CAMS / AGG / WEST / IL */}
        <ConflictFeedCell />

      </div>

      {/* ── ROW 2: Full-width Intel Panels ────────────────────────────────── */}
      <div style={{ display: "flex", flexDirection: "column", overflow: "hidden", borderBottom: "1px solid rgba(25,35,50,0.8)" }}>
        <div style={{ display: "flex", alignItems: "center", flexShrink: 0,
          borderBottom: "1px solid rgba(25,35,50,0.5)", background: "rgba(4,8,16,0.95)" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#a3b9ca",
            padding: "0 8px", flexShrink: 0, letterSpacing: 1 }}>INTEL</span>
          {panelOrder.map(p => {
            const m = PANEL_META[p];
            const on = p === activePanel;
            return (
              <button key={p} onClick={() => { setActivePanel(p); setPanelCycling(false); }} style={{
                flex: 1, padding: "5px 3px",
                background: on ? `${m.color}10` : "transparent",
                border: "none",
                borderTop: `2px solid ${on ? m.color : "transparent"}`,
                color: on ? m.color : "#829aae",
                fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
                letterSpacing: 0.6, cursor: "pointer", transition: "all 0.15s",
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}>
                {m.icon} {m.label}
              </button>
            );
          })}
          <button aria-label={panelCycling?"Pause panel rotation":"Start panel rotation"} onClick={() => setPanelCycling(c => !c)} style={{
            padding: "5px 8px", background: "transparent", border: "none", flexShrink: 0,
            color: panelCycling ? "#3fb950" : "#829aae",
            fontFamily: "var(--font-mono)", fontSize: 11, cursor: "pointer",
          }}>
            <span aria-hidden="true">{panelCycling ? "⏸" : "▶"}</span>
          </button>
        </div>

        <div style={{ flex: 1, overflow: "hidden" }}>
          {activePanel === "breaking"  && <BreakingIntelPanel events={events} clock={clock} />}
          {activePanel === "sources"   && <SourceIntelPanel events={events} clock={clock} />}
          {activePanel === "threats"   && <ThreatMatrixPanel events={events} clock={clock} />}
          {activePanel === "radiation" && (
            <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
              <div style={{ padding: "6px 12px", borderBottom: "1px solid rgba(63,185,80,0.15)",
                flexShrink: 0, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
                  letterSpacing: 1.5, color: "#3fb950" }}>☢ RADIATION MONITOR</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#8b9eaf" }}>RADMON.ORG GLOBAL NETWORK</span>
              </div>
              <MediaFrame src="https://radmon.org/index.php" style={{ flex: 1, border: "none", background: "#050a0f" }}
                title="Radiation Monitor" loading="lazy" />
            </div>
          )}
        </div>
      </div>

      {/* ── ROW 3: SITREP Source Intel Horizontal Scroll ─────────────────── */}
      <div style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "4px 12px", borderBottom: "1px solid rgba(25,35,50,0.6)", flexShrink: 0,
          display: "flex", alignItems: "center", gap: 10, background: "rgba(4,8,16,0.97)" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
            letterSpacing: 1.5, color: "#f85149" }}>BRIEFING SOURCE RECORDS</span>
          {sitrepMeta && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#829aae" }}>
              ID #{sitrepMeta.id} · {sitrepEvents.length} REPORTS · {
                (() => { const m = Math.round((nowMs() - new Date(sitrepMeta.generated_at).getTime()) / 60000);
                  return m < 60 ? `${m}m ago` : `${Math.round(m/60)}h ago`; })()
              } — CLICK TO VIEW SOURCE
            </span>
          )}
        </div>
        {sourceStatus==="unavailable"&&sitrepEvents.length>0&&<p role="status">Source references unavailable · retained records may be stale</p>}
        <div style={{ flex: 1, display: "flex", gap: 6, padding: "5px 10px",
          overflowX: "auto", overflowY: "hidden", alignItems: "stretch" }}>
          {sitrepEvents.map((evt: any) => {
            const sev = evt.severity || 0;
            const sc = !isScored(evt)?"#a3b9ca":sev >= 8 ? "#f85149" : sev >= 6 ? "#f0883e" : sev >= 4 ? "#d29922" : "#91c9e8";
            const url=safeUrl(evt.source_url);const hasUrl=!!url;
            const srcLabel = (evt.source || "")
              .replace("rss_x_", "@").replace("rss_", "").replace(/_/g, " ").toUpperCase().slice(0, 20);
            const ago=sourceAge(evt.timestamp,clock);
            return (
              <a key={evt.id} href={url||undefined} target={hasUrl ? "_blank" : "_self"}
                rel="noopener noreferrer"
                style={{ minWidth: 240, maxWidth: 270, flexShrink: 0, textDecoration: "none",
                  background: "rgba(5,9,16,0.85)",
                  border: `1px solid ${sev >= 7 ? sc + "55" : "#1a2a3a"}`,
                  borderLeft: `3px solid ${sc}`,
                  borderRadius: 3, padding: "6px 8px",
                  display: "flex", flexDirection: "column", gap: 4,
                  cursor: hasUrl ? "pointer" : "default",
                  transition: "background 0.15s",
                }}
                onMouseEnter={e => hasUrl && ((e.currentTarget as HTMLElement).style.background = `${sc}12`)}
                onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = "rgba(5,9,16,0.85)")}
              >
                {/* Top row: source + badges + time */}
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
                    color: sc, letterSpacing: 0.8, flex: 1,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {srcLabel}
                  </span>

                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11,
                    color: "#8b9eaf", flexShrink: 0 }}>{ago}</span>
                </div>
                {/* Headline */}
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600,
                  color: "#d0d8e4", lineHeight: 1.45,
                  overflow: "hidden", display: "-webkit-box",
                  WebkitLineClamp: 3, WebkitBoxOrient: "vertical" as any,
                  flex: 1 }}>
                  {evt.summary}
                </div>
                {/* Footer: sev + link */}
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
                    color: sc, background: `${sc}18`, padding: "1px 5px", borderRadius: 2 }}>
                    {severityLabel(evt)}
                  </span>
                  {hasUrl && (
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#8ea8be",
                      marginLeft: "auto" }}>↗ SOURCE</span>
                  )}
                </div>
              </a>
            );
          })}
          {sitrepEvents.length === 0 && (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#829aae",
              display: "flex", alignItems: "center", padding: "0 20px" }}>
              {sourceStatus==="loading"?"Loading briefing source records…":sourceStatus==="unavailable"?"Source references unavailable · retrying":"No source records available for this briefing"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
