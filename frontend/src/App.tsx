import {reportSourceKind} from "./lib/events";
import {SourceStatus} from "./components/SourceStatus";
import {briefScore,briefIndexLabel,isSourceDigest} from "./lib/brief";
import { SettingsPanel } from "./components/SettingsPanel";
import { nowMs } from "./lib/clock";
import { SHOWCASE, safeUrl } from "./lib/runtime";
import { ShowcaseBar } from "./components/ShowcaseBar";
import { ShowcaseBriefing } from "./components/MediaFrame";
import { apiFetch } from "./lib/api";
import { API_BASE } from "./lib/runtime";
import { MEDIA_BASE } from "./lib/runtime";
import React from 'react';
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Header } from "./components/Header";
import { LiveFeed } from "./components/LiveFeed";
import {workspaceView,type ViewMode} from "./lib/workspace";
import { TimelineScrubber } from "./components/TimelineScrubber";
import { MarketStrip } from "./components/MarketStrip";
import { AboutPanel } from "./components/AboutPanel";
import { useEventStream } from "./hooks/useEventStream";
import { useTracking } from "./hooks/useTracking";
import { useEarthProvider } from "./hooks/useEarthProvider";
import {LocalBriefingPanel} from "./components/LocalBriefingPanel";
import {useWorkspacePanelFocus} from "./hooks/useWorkspacePanelFocus";
import {useModalFocus} from "./hooks/useModalFocus";
import {reportImageryLinks,sourceFamily} from "./lib/reportPresentation";

const CesiumView = lazy(() => import("./components/CesiumView").then(m => ({ default: m.CesiumView })));
const IntelMediaView = lazy(() => import("./components/IntelMediaView").then(m => ({ default: m.IntelMediaView })));

export type {ViewMode} from "./lib/workspace";


const SITREP_VIDEO_BASE = MEDIA_BASE;

const LEVEL_COLORS: Record<string, string> = {
  STABLE: "#3fb950", ELEVATED: "#d29922", ESCALATING: "#f0883e", CRITICAL: "#f85149", WARTIME: "#ff0044",
};
const LEVEL_BG: Record<string, string> = {
  STABLE: "#0d1f12", ELEVATED: "#1a1600", ESCALATING: "#1a0e00", CRITICAL: "#1a0000", WARTIME: "#200008",
};
const mono = "var(--font-mono)";

// ── Mobile detection hook ──────────────────────────────────────────────────────
function useIsMobile() {
  const check = () => ({
    isMobile: window.innerWidth <= 768 || (window.innerWidth<=900&&window.innerHeight<=500),
    isLandscape: window.innerWidth > window.innerHeight && window.innerHeight <= 500,
    isOverlay: window.innerWidth <= 1100,
  });
  const [state, setState] = useState(check);
  useEffect(() => {
    const update = () => setState(check());
    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
    };
  }, []);
  return state;
}

// ── Mobile bottom navigation bar ───────────────────────────────────────────────
const MOBILE_NAV_ITEMS: { mode: ViewMode; label: string; icon: string; pulse?: string }[] = [
  { mode: "earth", label: "Earth", icon: "◉" },
  { mode: "media",  label: "Media",  icon: "📡", pulse: "#58a6ff" },
  { mode: "sitrep", label: "Brief", icon: "◈",  pulse: "#f85149" },
];

function MobileNav({ viewMode, onViewModeChange, onOpenFeed, reportCount = 0 }: {
  viewMode: ViewMode;
  onViewModeChange: (m: ViewMode) => void;
  onOpenFeed?: () => void;
  reportCount?: number;
}) {
  return (
    <nav className="mobile-bottom-nav" aria-label="View navigation">
      {MOBILE_NAV_ITEMS.map(({ mode, label, icon, pulse }) => {
        const active = viewMode === mode;
        const color = pulse ?? "#58a6ff";
        return (
          <button
            key={mode}
            onClick={() => onViewModeChange(mode)}
            aria-pressed={active}
            style={{
              flex: 1, background: "none", border: "none",
              display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center",
              gap: 3, cursor: "pointer", position: "relative",
              color: active ? color : "var(--text-secondary)",
              transition: "color 0.15s",
              minHeight: 56, padding: "0 4px",
              WebkitTapHighlightColor: "transparent",
            }}
          >
            {active && (
              <div style={{
                position: "absolute", top: 0, left: "15%", right: "15%",
                height: 2, background: color,
                borderRadius: "0 0 2px 2px",
                boxShadow: `0 0 6px ${color}88`,
              }} />
            )}
            <span style={{ fontSize: 20, lineHeight: 1 }}>{icon}</span>
            <span style={{
              fontSize: 11, fontFamily: mono, letterSpacing: 1.2,
              fontWeight: 700, lineHeight: 1,
            }}>{label}</span>
          </button>
        );
      })}
      {onOpenFeed && <button className="feed-fab" onClick={onOpenFeed} title="Open report feed" aria-label={`Feed${reportCount>0?(reportCount>99?"99+":reportCount):""} — open report feed`}>
        <span aria-hidden="true" style={{fontSize:20,lineHeight:1}}>⚡</span>
        <span style={{fontSize:11,fontFamily:mono,letterSpacing:1.2,fontWeight:700,lineHeight:1}}>FEED</span>
        {reportCount>0 && <span className="mobile-feed-count" aria-hidden="true">{reportCount>99?"99+":reportCount}</span>}
      </button>}
    </nav>
  );
}

// ── Feed sheet (slide-up live feed panel on portrait mobile) ───────────────────
function FeedSheet({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  const startY = useRef<number|null>(null);
  const sheetRef = useModalFocus(true,onClose);

  const onTouchStart = (e: React.TouchEvent) => {
    // Scroll gestures in the report list belong to the native scroll surface.
    const dragHandle=e.target instanceof Element&&e.target.closest('.feed-sheet-handle,.feed-sheet-header');
    startY.current=dragHandle&&!((e.target as Element).closest('button'))?e.touches[0]?.clientY??null:null;
  };
  const onTouchEnd   = (e: React.TouchEvent) => {
    const start=startY.current;startY.current=null;
    if (start!==null&&e.changedTouches[0]&&e.changedTouches[0].clientY-start>60) onClose();
  };

  // Close on backdrop click
  const onBackdrop = (e: React.MouseEvent) => { if (e.target === e.currentTarget) onClose(); };

  return (
    <div
      onClick={onBackdrop}
      style={{
        position: "fixed", inset: 0,
        zIndex: 149,
        background: "rgba(0,0,0,0.45)",
        backdropFilter: "blur(2px)",
      }}
    >
      <div
        ref={sheetRef}
        className="feed-sheet"
        role="dialog" aria-modal="true" aria-label="Report feed" tabIndex={-1}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        <div className="feed-sheet-handle" />
        <div className="feed-sheet-header" style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 14px 6px", flexShrink: 0,
        }}>
          <span style={{ fontSize: 11, fontFamily: mono, letterSpacing: 2, color: "var(--text-secondary)", fontWeight: 700 }}>
            REPORT FEED
          </span>
          <button data-modal-close aria-label="Close report feed" onClick={onClose} style={{
            background: "none", border: "none", color: "var(--text-secondary)",
            fontSize: 18, cursor: "pointer", lineHeight: 1, padding: "4px 8px",minWidth:44,minHeight:44,
          }}>×</button>
        </div>
        <div className="feed-sheet-body">{children}</div>
      </div>
    </div>
  );
}

function timeAgo(iso: string) {
  const time=Date.parse(iso);if(!Number.isFinite(time))return "Time unknown";if(time>nowMs())return "Future source time";
  const m = Math.round((nowMs() - new Date(iso).getTime()) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  if (m < 1440) return `${Math.round(m / 60)}h ago`;
  return `${Math.round(m / 1440)}d ago`;
}

function fmtDate(iso: string) {
  if(!Number.isFinite(Date.parse(iso)))return "Time unknown";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    hour12: false, timeZone: "UTC",
  }) + " UTC";
}

function SitrepBroadcastView({ style }: { style?: React.CSSProperties }) {
  const { isMobile } = useIsMobile();
  const API = API_BASE;
  const [sitrep, setSitrep] = useState<any>(null);
  const [sitrepEvents, setSitrepEvents] = useState<any[]>([]);
  const [briefStatus,setBriefStatus]=useState<"loading"|"ready"|"empty"|"unavailable">("loading");
  const [sitrepList, setSitrepList] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [eventSourceMap, setEventSourceMap] = useState<Record<number, string>>({});
  const [videoKey, setVideoKey] = useState(nowMs());
  const loadController=useRef<AbortController|null>(null);
  const [briefSourceStatus,setBriefSourceStatus]=useState<"loading"|"ready"|"empty"|"unavailable">("loading");
  useEffect(()=>()=>loadController.current?.abort(),[]);
  const [showIntelBrief, setShowIntelBrief] = useState(false);
  const [videoManifest, setVideoManifest] = useState<Record<string, {url: string; generated_at: string}>>({});
  const [videoModalUrl, setVideoModalUrl] = useState<string | null>(null);
  const modalRef=useModalFocus(showIntelBrief||videoModalUrl!==null,()=>{setShowIntelBrief(false);setVideoModalUrl(null);});
  const [sentinelHubInstanceId, setSentinelHubInstanceId] = useState("");
  const [videoEnabled,setVideoEnabled]=useState(SHOWCASE);

  // Fetch Sentinel Hub instance ID for satellite WMS thumbnails
  useEffect(() => {
    apiFetch(`${API}/config`).then(r => r.json()).then(d => {
      setVideoEnabled(SHOWCASE||d.video_generation_enabled===true);
      if (d.sentinel_hub_instance_id) setSentinelHubInstanceId(d.sentinel_hub_instance_id);
    }).catch(() => {});
  }, [API]);

  // Refresh video manifest (callable from anywhere)
  const refreshManifest = useCallback(() => {
    if(!videoEnabled)return;
    apiFetch(MEDIA_BASE + '/videos/manifest.json?t=' + nowMs())
      .then(r => r.json())
      .then(d => { if (d && typeof d === 'object') setVideoManifest(d); })
      .catch(() => {});
  }, [videoEnabled]);

  // A selected briefing and its source rows share one cancellable request generation.
  const loadSitrep = useCallback(async (id?: number) => {
    loadController.current?.abort();const controller=new AbortController();loadController.current=controller;
    setBriefSourceStatus("loading");setSitrepEvents([]);setEventSourceMap({});
    try {
      const url=id?`${API}/sitreps/${id}`:`${API}/sitreps/latest`;
      const r=await apiFetch(url,{signal:controller.signal});if(!r.ok)throw Error();const j=await r.json();if(controller.signal.aborted)return;
      const s=j.sitrep||j;setBriefStatus(s?.id?"ready":"empty");
      if(!s?.id){setSitrep(null);setBriefSourceStatus("empty");return;}
      setSitrep(s);setSelectedId(s.id);refreshManifest();
      try{
        const er=await apiFetch(`${API}/sitreps/${s.id}/events`,{signal:controller.signal});if(!er.ok)throw Error();const ej=await er.json();const rows=Array.isArray(ej)?ej:ej.events;
        if(!Array.isArray(rows))throw Error();if(controller.signal.aborted)return;
        setSitrepEvents(rows);setBriefSourceStatus(rows.length?"ready":"empty");const map:Record<number,string>={};for(const row of rows){const url=safeUrl(row.source_url);if(url)map[row.id]=url;}setEventSourceMap(map);
      }catch{if(!controller.signal.aborted)setBriefSourceStatus("unavailable");}
    }catch{if(!controller.signal.aborted){setBriefStatus("unavailable");setBriefSourceStatus("unavailable");}}
  }, [API, refreshManifest]);

  // Load SITREP history list
  useEffect(() => {
    apiFetch(`${API}/sitreps/?limit=25`)
      .then(r => r.json())
      .then(d => { if (Array.isArray(d)) setSitrepList(d); })
      .catch(() => {});
  }, []);

  // Load video manifest on mount + refresh every 2 min
  useEffect(() => {
    refreshManifest();
    const t = setInterval(refreshManifest, 2 * 60 * 1000);
    return () => clearInterval(t);
  }, [refreshManifest]);

  useEffect(() => {
    loadSitrep();
    const t = setInterval(() => loadSitrep(), 5 * 60 * 1000);
    return () => clearInterval(t);
  }, [loadSitrep]);

  useEffect(() => {
    const t = setInterval(() => setVideoKey(nowMs()), 5 * 60 * 1000);
    return () => clearInterval(t);
  }, []);

  const level = sitrep?.escalation_level || "UNASSESSED";
  const lc = LEVEL_COLORS[level] || "#58a6ff";
  const lb = LEVEL_BG[level] || "#030508";

  const briefEmptyText=briefStatus==="unavailable"?"Briefing service unavailable · retrying":briefStatus==="empty"?"No source briefing yet · collecting dated reports":"Loading source briefing…";

  // Parse inline [src:8206,8221] refs → clickable footnotes
  function parseRefs(text: string): React.ReactNode {
    if (!text) return text;
    const parts = text.split(/(\[src:[^\]]+\])/g);
    let footIdx = 0;
    return parts.map((part, i) => {
      const match = part.match(/^\[src:([^\]]+)\]$/);
      if (!match) return <React.Fragment key={i}>{part}</React.Fragment>;
      const ids = match[1].split(",").map(Number).filter(Boolean);
      return (
        <span key={i} style={{ display: "inline" }}>
          {ids.map((id) => {
            footIdx++;
            const url = eventSourceMap[id];
            const n = footIdx;
            return url ? (
              <a key={id} href={safeUrl(url)} target="_blank" rel="noopener noreferrer"
                title={`Source event #${id}`}
                style={{ color: lc, fontSize: "0.7em", verticalAlign: "super",
                  marginLeft: 1, textDecoration: "none", opacity: 0.85,
                  fontWeight: 700, cursor: "pointer" }}>
                [{n}]
              </a>
            ) : (
              <span key={id} style={{ fontSize: "0.65em", verticalAlign: "super",
                marginLeft: 1, color: "#8da3b7" }}>[{n}]</span>
            );
          })}
        </span>
      );
    });
  }

  const intelSections = sitrep ? [
    { icon: "▲", label: "ESCALATION ASSESSMENT", text: sitrep.escalation_text, color: "#f0883e" },
    { icon: "$", label: "ECONOMIC EXPOSURE",      text: sitrep.economic_exposure, color: "#d29922" },
    { icon: "⊕", label: "GAME THEORY ANALYSIS",  text: sitrep.game_theory,       color: "#bc8cff" },
    { icon: "♥", label: "HUMANITARIAN GROUND",   text: sitrep.humanitarian_ground, color: "#3fb950" },
    { icon: "◷", label: "HISTORICAL ANALOGUE",   text: sitrep.historical_analogue, color: "#58a6ff" },
  ].filter(s => s.text) : [];

  // SITREP age warning
  const isStale = sitrep && (nowMs() - new Date(sitrep.generated_at).getTime()) > 6 * 3600000;

  // Resolve video URL for selected SITREP
  const currentVideoEntry = selectedId ? videoManifest[String(selectedId)] : null;
  const hasVideoForSelected = !!currentVideoEntry;
  const currentVideoUrl = currentVideoEntry
    ? MEDIA_BASE + currentVideoEntry.url + "?t=" + videoKey
    : null;
  const currentVideoLabel = currentVideoEntry
    ? "SITREP #" + selectedId + " BRIEFING"
    : isSourceDigest(sitrep)?"SOURCE BRIEFING · TEXT ONLY":"NO VIDEO AVAILABLE";
  // Is this SITREP recent enough that video might still be generating? (< 35 min)
  const isRecentSitrep = !SHOWCASE && sitrep && !isSourceDigest(sitrep) &&
    (nowMs() - new Date(sitrep.generated_at).getTime()) < 35 * 60 * 1000;

  return (
    <div className="brief-desk" style={{
      ...style, minWidth: 0,
      display: "grid",
      gridTemplateRows: "44px 112px minmax(360px,1fr)",
      minHeight:560,
      background: "#030508",
      overflow: "hidden",
      fontFamily: mono,
    }}>

      {/* ── TOP ALERT BANNER ── */}
      <div className="brief-status" style={{
        display: "flex", alignItems: "center", gap: 10, padding: "0 14px",
        background: `linear-gradient(90deg, ${lb} 0%, #030508 60%)`,
        borderBottom: `2px solid ${lc}55`, flexShrink: 0,
      }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: lc, flexShrink: 0,
          animation: "statusPulse 1.5s infinite", boxShadow: `0 0 10px ${lc}` }} />
        <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: 2, color: "#030508",
          background: lc, padding: "2px 8px", borderRadius: 2, flexShrink: 0 }}>{level}</span>
        <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: 2, color: lc }}>{briefStatus==="unavailable"?"BRIEF UNAVAILABLE · RETAINED":isSourceDigest(sitrep)?"▤ SOURCE BRIEFING":"◈ SITUATION BRIEF"}</span>
        {sitrep && (
          <>
            <span style={{ fontSize: 11, color: "#a3b9ca" }}>│</span>
            <span style={{ fontSize: 11, color: "#a3b9ca" }}>ID #{sitrep.id}</span>
            <span style={{ fontSize: 11, color: "#a3b9ca" }}>·</span>
            <span style={{ fontSize: 11, color: isStale ? "#f0883e" : "#5a7a9a" }}>{timeAgo(sitrep.generated_at)}</span>
            {isStale && <span style={{ fontSize: 11, color: "#f0883e", background: "rgba(240,136,62,0.12)",
              padding: "1px 6px", borderRadius: 2, fontWeight: 700 }}>⚠ STALE</span>}
            <span style={{ fontSize: 11, color: "#a3b9ca" }}>·</span>
            <span style={{ fontSize: 11, color: lc, fontWeight: 700 }}>{sitrep.events_analyzed} REPORTS {isSourceDigest(sitrep)?"COMPILED":"ANALYZED"}</span>
            <span style={{ fontSize: 11, color: "#a3b9ca" }}>│</span>
            <span style={{ fontSize: 11, color: lc, background: `${lc}18`, padding: "1px 7px",
              borderRadius: 2, fontFamily: mono, fontWeight: 700, letterSpacing: 0.5 }}>
              INDEX {briefIndexLabel(sitrep)}
            </span>
          </>
        )}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "#8b9eaf" }}>
            {sitrep ? fmtDate(sitrep.generated_at) : "—"}
          </span>
          {sitrep && (
            <button onClick={() => setShowIntelBrief(true)} style={{
              background: `${lc}20`, border: `1px solid ${lc}66`, borderRadius: 3,
              color: lc, fontSize: 11, fontFamily: mono, letterSpacing: 1,
              padding: "3px 10px", cursor: "pointer", fontWeight: 800,
              boxShadow: `0 0 8px ${lc}22`,
              display: "flex", alignItems: "center", gap: 5,
            }}>
              <span style={{ fontSize: 11 }}>◈</span>
              <span>INTEL BRIEF</span>
            </button>
          )}
        </div>
      </div>

      {/* ── SITREP HISTORY CARDS ── */}
      <div style={{
        display: "flex", alignItems: "stretch", overflow: "hidden",
        background: "rgba(2,4,10,0.99)", borderBottom: "1px solid #0d1a26",
        height: 112,
      }}>
        {/* Left label column */}
        <div style={{
          display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center",
          padding: "0 10px", borderRight: "1px solid #0d1a26", flexShrink: 0, gap: 2, minWidth: 52,
        }}>
          <span style={{ fontSize: 11, color: "#a3b9ca", letterSpacing: 1.5, writingMode: "vertical-rl",
            transform: "rotate(180deg)", textTransform: "uppercase", userSelect: "none" }}>INTEL HISTORY</span>
          <span style={{ fontSize: 11, color: "#a3b9ca", letterSpacing: 1 }}>{sitrepList.length} RPTS</span>
        </div>

        {/* Horizontally scrollable SITREP cards */}
        <div role="region" aria-label="Source briefing history" tabIndex={0} style={{
          flex: 1, display: "flex", gap: 5, overflowX: "auto", overflowY: "hidden",
          padding: "6px 8px", alignItems: "stretch",
          scrollbarWidth: "thin", scrollbarColor: "#1a2a3a transparent",
        }}>
          {[...sitrepList].sort((a: any, b: any) => b.id - a.id).map((s: any) => {
            const sc2 = briefScore(s);
            const slc = LEVEL_COLORS[s.escalation_level as string] || "#58a6ff";
            const isSel = s.id === selectedId;
            const hasVid = !!videoManifest[String(s.id)];
            const headline = s.headline || "";
            const sorted2 = [...sitrepList].sort((a: any, b: any) => b.id - a.id);
            const idx2 = sorted2.findIndex((x: any) => x.id === s.id);
            const prev2 = sorted2[idx2 + 1];
            const previousScore=briefScore(prev2);
            const delta2 = sc2!==null&&previousScore!==null?sc2-previousScore:0;

            return (
              <div key={s.id} style={{flexShrink:0,width:152,display:"flex",flexDirection:"column",gap:3}}>
              <button type="button" className="sitrep-history-card"
                onClick={() => loadSitrep(s.id)}
                style={{
                  flex:1,minHeight:0,width:152,fontFamily:"inherit",color:"inherit",textAlign:"left",
                  display: "flex", flexDirection: "column", gap: 4,
                  background: isSel ? `${slc}14` : "rgba(4,8,18,0.85)",
                  border: `1px solid ${isSel ? slc + "55" : "#0d1a2a"}`,
                  borderRadius: 4, padding: "6px 8px",
                  cursor: "pointer", transition: "all 0.15s",
                  boxShadow: isSel ? `0 0 10px ${slc}22, inset 0 0 0 1px ${slc}33` : "none",
                  position: "relative",
                }}
              >
                {/* Top row: level badge + ID + video icon */}
                <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                  <span style={{
                    fontSize: 11, fontWeight: 800, letterSpacing: 0.5,
                    padding: "1px 5px", borderRadius: 2,
                    background: `${slc}22`, color: slc, flexShrink: 0,
                  }}>{s.escalation_level}</span>
                  <span style={{ fontSize: 11, color: "#a3b9ca", marginLeft: "auto", flexShrink: 0 }}>
                    #{s.id}
                  </span>
                  {hasVid&&<span aria-hidden="true" title="Recording available">▶</span>}
                </div>

                {/* Headline text */}
                <div style={{
                  flex: 1, fontSize: 11, color: isSel ? "#c9d1d9" : "#9ab5cc",
                  lineHeight: 1.38, overflow: "hidden",
                  display: "-webkit-box", WebkitLineClamp: 3,
                  WebkitBoxOrient: "vertical" as any,
                  transition: "color 0.15s",
                }}>
                  {headline || <span style={{ color: "#a3b9ca", fontStyle: "italic" }}>No headline</span>}
                </div>

                {/* Bottom row: score + delta + time */}
                <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                  <span style={{
                    fontSize: 11, fontWeight: 800, color: slc, fontFamily: mono, letterSpacing: 0.5,
                  }}>
                    {sc2??"Unassessed"}
                    {delta2 !== 0 && (
                      <span style={{ fontSize: 11, fontWeight: 700, marginLeft: 2,
                        color: delta2 > 0 ? "#f85149" : "#3fb950" }}>
                        {delta2 > 0 ? "▲" : "▼"}{Math.abs(delta2)}
                      </span>
                    )}
                  </span>
                  <span style={{ fontSize: 11, color: "#a3b9ca", marginLeft: "auto", fontFamily: mono }}>
                    {timeAgo(s.generated_at)}
                  </span>
                </div>

                {/* Left accent border for selected */}
                {isSel && (
                  <div style={{
                    position: "absolute", left: 0, top: 0, bottom: 0,
                    width: 3, background: slc, borderRadius: "3px 0 0 3px",
                  }} />
                )}
              </button>
              {hasVid&&<button onClick={()=>setVideoModalUrl(MEDIA_BASE+videoManifest[String(s.id)].url)} aria-label={`Play recording for briefing ${s.id}`} style={{minHeight:28,border:"1px solid #395360",background:"#102331",color:"#c5e3e1",fontFamily:mono,fontSize:11,borderRadius:3,cursor:"pointer"}}>Play recording</button>}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── MAIN CONTENT ── */}
      <div className="brief-main" style={{
        display: "grid",
        gridTemplateColumns: "minmax(0,1fr)",
        overflow: "hidden",
        flex: 1, minHeight: 0,
      }}>

        {/* ═══ Video + Source Events (full width) ═══ */}
        <div className="brief-content" style={{
          display: "grid",
          gridTemplateRows: "55fr 45fr",
          overflow: "hidden", minWidth: 0,
        }}>

          {/* ── Video + Action Panel (2 columns) ── */}
          <div className="brief-context-grid" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", overflow: "hidden", minWidth: 0 }}>

            {/* LEFT: Video column */}
            <div className="brief-video" style={{ display: "flex", flexDirection: "column", background: "#000", overflow: "hidden", minWidth: 0, borderRight: `1px solid ${lc}22` }}>
            {/* Header bar */}
            <div style={{ padding: "5px 10px", flexShrink: 0, display: "flex", alignItems: "center", gap: 8,
              background: `linear-gradient(90deg, ${lc}18 0%, rgba(3,5,8,0.95) 100%)`,
              borderBottom: `1px solid ${lc}33` }}>
              <span style={{
                width: 6, height: 6, borderRadius: "50%",
                background: hasVideoForSelected ? "#f85149" : "#2a3a4a",
                animation: hasVideoForSelected ? "statusPulse 1.2s infinite" : "none",
              }} />
              <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: 2,
                color: hasVideoForSelected ? "#e6edf3" : "#8da3b7" }}>{currentVideoLabel}</span>
              {hasVideoForSelected && (
                <span style={{ fontSize: 11, color: lc, background: `${lc}18`, padding: "1px 6px",
                  borderRadius: 2, fontWeight: 700, letterSpacing: 1 }}>{isSourceDigest(sitrep)?"ATTRIBUTED DIGEST":"DATED ANALYSIS"}</span>
              )}
              <span style={{ fontSize: 11, color: "#8da3b7", marginLeft: "auto" }}>
                {sitrep ? fmtDate(sitrep.generated_at) : briefEmptyText}
              </span>
            </div>

            {/* Video player (only when video available) */}
            {hasVideoForSelected && currentVideoUrl && (
              <video key={String(selectedId)} controls autoPlay preload="metadata"
                style={{ flex: 1, objectFit: "contain", display: "block", minHeight: 0, background: "#000" }}>
                <source src={currentVideoUrl} type="video/mp4" />
              </video>
            )}

            {/* Placeholder when no video */}
            {SHOWCASE && <ShowcaseBriefing />}
            {!SHOWCASE && !hasVideoForSelected && (
              <div style={{
                flex: 1, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center",
                background: "linear-gradient(180deg, #020406 0%, #030810 100%)",
                padding: "20px 24px", gap: 14, minHeight: 0, overflow: "hidden",
              }}>
                {/* Branding */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                  <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: 4, color: lc, opacity: 1,
                    fontFamily: mono }}>◈ CONFLICT MONITOR</div>
                  <div style={{ width: 32, height: 1, background: `${lc}33` }} />
                </div>

                {/* SITREP content preview */}
                {sitrep && (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center",
                    gap: 8, maxWidth: 340, textAlign: "center" }}>
                    {/* Level + score badge */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 800, color: lc, background: `${lc}20`,
                        padding: "2px 8px", borderRadius: 2, letterSpacing: 1 }}>
                        {sitrep.escalation_level}
                      </span>
                      <span style={{ fontSize: 11, color: lc, fontFamily: mono, fontWeight: 700,
                        opacity: 0.7 }}>
                        INDEX {briefIndexLabel(sitrep)}
                      </span>
                    </div>
                    {/* Headline */}
                    <div style={{
                      fontSize: 12, fontWeight: 700, color: "#8a9ab5", lineHeight: 1.5,
                      fontFamily: "var(--font-sans, system-ui)",
                    }}>
                      {sitrep.headline}
                    </div>
                    {/* Status message */}
                    <div style={{ fontSize: 11, color: "#a3b9ca", fontFamily: mono, letterSpacing: 1 }}>
                      {isRecentSitrep
                        ? "⟳  VIDEO BRIEFING GENERATING..."
                        : "VIDEO BRIEFING NOT AVAILABLE FOR THIS SITREP"}
                    </div>
                    {isRecentSitrep && (
                      <div style={{ fontSize: 11, color: "#a3b9ca" }}>
                        Check back in a few minutes
                      </div>
                    )}
                  </div>
                )}

                {/* Subtle grid decoration */}
                <div style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden",
                  opacity: 0.04 }}>
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} style={{ position: "absolute", left: `${i * 14.3}%`,
                      top: 0, bottom: 0, width: 1, background: lc }} />
                  ))}
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} style={{ position: "absolute", top: `${i * 25}%`,
                      left: 0, right: 0, height: 1, background: lc }} />
                  ))}
                </div>
              </div>
            )}
            </div>{/* end video column */}

            {/* RIGHT: Intel panel */}
            <div className="brief-context" role="region" aria-label="Briefing context and sources" tabIndex={0} style={{
              display: "flex", flexDirection: "column", overflowY: "auto", minHeight: 0, minWidth: 0,
              background: "#020508", borderLeft: `1px solid ${lc}18`,
            }}>

              {/* ── Header bar ── */}
              <div style={{
                padding: "6px 14px", flexShrink: 0,
                background: `linear-gradient(90deg, ${lc}12 0%, transparent 100%)`,
                borderBottom: `1px solid ${lc}22`,
                display: "flex", alignItems: "center", justifyContent: "space-between",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: lc,
                    animation: "statusPulse 2s infinite", display: "inline-block", flexShrink: 0 }} />
                  <span style={{ fontSize: 11, fontWeight: 800, color: lc, letterSpacing: 2, fontFamily: mono }}>
                    INTEL PANEL
                  </span>
                </div>
                {sitrep && (
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 11, color: lc, background: `${lc}20`,
                      padding: "2px 7px", borderRadius: 2, fontWeight: 800, letterSpacing: 0.8 }}>{level}</span>
                    <span style={{ fontSize: 11, fontWeight: 800, color: lc, fontFamily: mono }}>
                      {briefIndexLabel(sitrep)}
                    </span>
                  </div>
                )}
              </div>

              {/* ── Escalation bar + headline ── */}
              {sitrep && (
                <div style={{ padding: "8px 14px 7px", flexShrink: 0, borderBottom: `1px solid #0c1822` }}>
                  <div style={{ height: 2, borderRadius: 2, background: "#080f18", overflow: "hidden", marginBottom: 6 }}>
                    <div style={{
                      height: "100%", borderRadius: 2,
                      width: `${briefScore(sitrep)??0}%`,
                      background: `linear-gradient(90deg, #d29922 0%, ${lc} 100%)`,
                      boxShadow: `0 0 6px ${lc}44`,
                    }} />
                  </div>
                  <div style={{ fontSize: 11, color: "#8a9eb8", lineHeight: 1.45, fontWeight: 500 }}>
                    {sitrep.headline}
                  </div>
                </div>
              )}

              {/* ── ◈ INTEL BRIEF button ── */}
              <div style={{ padding: "9px 14px 8px", flexShrink: 0, borderBottom: `1px solid #0c1822` }}>
                <button
                  onClick={() => setShowIntelBrief(true)}
                  style={{
                    width: "100%", padding: "10px 0",
                    background: `linear-gradient(135deg, ${lc}22 0%, ${lc}0e 100%)`,
                    border: `1px solid ${lc}55`,
                    borderRadius: 4, cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                    boxShadow: `0 0 18px ${lc}18, inset 0 0 0 1px ${lc}0a`,
                    transition: "box-shadow 0.15s",
                  }}
                >
                  <span style={{ fontSize: 13, color: lc }}>◈</span>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 1 }}>
                    <span style={{ fontSize: 11, fontWeight: 800, color: lc, letterSpacing: 1.5, fontFamily: mono }}>
                      {isSourceDigest(sitrep)?"OPEN SOURCE BRIEFING":"OPEN INTEL BRIEF"}
                    </span>
                    <span style={{ fontSize: 11, color: lc, opacity: 1, letterSpacing: 0.5 }}>
                      {isSourceDigest(sitrep)?"Attributed report compilation · risk unassessed":"Generated situation analysis · unreviewed"}
                    </span>
                  </div>
                </button>
              </div>

              {/* ── Intelligence assessment bullets ── */}
              {intelSections.length > 0 && (
                <div style={{ flexShrink: 0, borderBottom: `1px solid #0c1822` }}>
                  <div style={{ padding: "5px 14px 4px", display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ fontSize: 11, fontWeight: 800, color: "#a3b9ca", letterSpacing: 1.8, fontFamily: mono }}>
                      KEY ASSESSMENTS
                    </span>
                  </div>
                  {intelSections.slice(0, 3).map((sec, idx) => (
                    <div key={idx} style={{
                      padding: "5px 14px 5px 11px",
                      borderLeft: `2px solid ${sec.color}44`,
                      margin: "0 0 1px 0",
                      background: idx % 2 === 0 ? "rgba(255,255,255,0.012)" : "transparent",
                    }}>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginBottom: 2 }}>
                        <span style={{ fontSize: 11, color: sec.color, fontWeight: 800, fontFamily: mono,
                          letterSpacing: 0.5, flexShrink: 0 }}>{sec.icon} {sec.label}</span>
                      </div>
                      <div style={{
                        fontSize: 11, color: "#7a8fa8", lineHeight: 1.5,
                        display: "-webkit-box", WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical" as const, overflow: "hidden",
                      }}>
                        {sec.text}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* References scroll with the context column instead of collapsing below its fixed sections. */}
              <div style={{ flexShrink: 0, display: "flex", flexDirection: "column" }}>
                <div style={{ padding: "5px 14px 4px", flexShrink: 0, display: "flex", alignItems: "center", gap: 6,
                  borderBottom: `1px solid #0a1520` }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: "#a3b9ca", letterSpacing: 1.8, fontFamily: mono }}>
                    SOURCE REFERENCES
                  </span>
                  <span style={{ fontSize: 11, color: lc, background: `${lc}18`, padding: "1px 5px",
                    borderRadius: 2, fontWeight: 700 }}>{sitrepEvents.filter(e => safeUrl(e.source_url) && !e.source_url.includes("copernicus")).length}</span>
                </div>
                <div role="region" aria-label="Briefing source references" tabIndex={0} style={{ padding: "3px 0" }}>
                  {sitrepEvents.length === 0 && (
                    <div style={{ padding: "12px 14px", fontSize: 11, color: "#a3b9ca", fontStyle: "italic" }}>
                      {briefSourceStatus==="unavailable"?"Source references unavailable · retrying":briefSourceStatus==="loading"?"Loading source references…":"No source records for this briefing"}
                    </div>
                  )}
                  {sitrepEvents.filter(e => safeUrl(e.source_url) && !e.source_url.includes("copernicus")).slice(0, 12).map((evt, i) => {
                    let domain = "";
                    try { domain = new URL(evt.source_url).hostname.replace("www.", ""); } catch {}
                    return (
                      <a
                        key={evt.id || i}
                        href={safeUrl(evt.source_url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          display: "block", padding: "7px 14px",
                          borderBottom: "1px solid #090f18",
                          textDecoration: "none",
                          background: "transparent",
                          transition: "background 0.1s",
                          cursor: "pointer",
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = `${lc}08`)}
                        onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 3 }}>
                          <span style={{ fontSize: 11, color: lc, background: `${lc}14`, padding: "1px 5px",
                            borderRadius: 2, fontFamily: mono, fontWeight: 700, flexShrink: 0 }}>
                            {domain || evt.source || "SRC"}
                          </span>
                          {evt.timestamp && (
                            <span style={{ fontSize: 11, color: "#a3b9ca", fontFamily: mono, marginLeft: "auto", flexShrink: 0 }}>
                              {timeAgo(evt.timestamp)}
                            </span>
                          )}
                        </div>
                        <div style={{
                          fontSize: 11, color: "#8a9eb8", lineHeight: 1.45,
                          display: "-webkit-box", WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical" as const, overflow: "hidden",
                        }}>
                          {evt.summary || evt.location_name || "—"}
                        </div>
                        {evt.location_name && (
                          <div style={{ fontSize: 11, color: "#a3b9ca", marginTop: 2, fontFamily: mono }}>
                            📍 {evt.location_name}
                          </div>
                        )}
                      </a>
                    );
                  })}
                </div>
              </div>

            </div>{/* end action panel */}

          </div>{/* end 2-col grid */}

          {/* Source Events */}
          <div className="brief-source-events" style={{ display: "flex", flexDirection: "column", overflow: "hidden", minHeight: 0, minWidth: 0,
            borderTop: `1px solid ${lc}22` }}>
            <div style={{ padding: "5px 10px", flexShrink: 0, display: "flex", alignItems: "center", gap: 8,
              background: "rgba(4,8,16,0.95)", borderBottom: "1px solid #1a2a3a" }}>
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1.5, color: "#a3b9ca" }}>⚡ SOURCE EVENTS</span>
              <span style={{ fontSize: 11, color: lc, background: `${lc}18`, padding: "1px 6px",
                borderRadius: 2, fontWeight: 700 }}>{sitrepEvents.length} REPORTS</span>
              <span style={{ fontSize: 11, color: "#a3b9ca", marginLeft: "auto" }}>
                Click to view source article
              </span>
            </div>
            <div role="region" aria-label="Briefing source events" tabIndex={0} style={{ flex: 1, overflowY: "auto", padding: "3px 0" }}>
              {sitrepEvents.length === 0 && (
                <div style={{ padding: "12px", fontSize: 11, color: "#8b9eaf", textAlign: "center" }}>
                  {sitrep?(briefSourceStatus==="unavailable"?"Source references unavailable · retrying":briefSourceStatus==="loading"?"Loading source references…":"No source records for this briefing"):briefEmptyText}
                </div>
              )}
              {sitrepEvents.map((evt: any, i: number) => {
                const sev = evt.severity || 0;
                const sc = sev >= 8 ? "#f85149" : sev >= 6 ? "#f0883e" : sev >= 4 ? "#d29922" : "#5a7a9a";
                const hasUrl = !!safeUrl(evt.source_url) && !evt.source_url.includes("copernicus");
                const isSatellite=sourceFamily(evt)==="sensor";
                const imagery=reportImageryLinks(evt),satUrl=imagery.google,copUrl=imagery.worldview;
                return (
                  <div key={evt.id || i}
                    style={{ display: "grid", gridTemplateColumns: "6px 1fr auto",
                      gap: 7, padding: "5px 10px", borderBottom: "1px solid #0d1a26",
                      background: isSatellite ? "rgba(88,166,255,0.04)" : "transparent",
                    }}
                  >
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: sc,
                      flexShrink: 0, marginTop: 3, alignSelf: "start" }} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 11, color: "#c9d1d9", lineHeight: 1.4,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {isSatellite && <span style={{ color: "#58a6ff", marginRight: 4, fontSize: 11 }}>📡</span>}
                        {evt.summary}
                      </div>
                      <div style={{ fontSize: 11, color: "#8da3b7", marginTop: 2, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                        <span style={{ color: "#a3b9ca", textTransform: "uppercase" }}>{evt.source}</span>
                        {isSatellite && (
                          <span style={{ color: "#58a6ff", fontWeight: 700 }}>⬡ SENSOR REPORTS</span>
                        )}
                        {evt.confirmed_networks && !isSatellite && (
                          <span style={{ color: "#a3b9ca" }} title="Inherited source tags do not establish independent origins or verify claims">Source tags: {evt.confirmed_networks}</span>
                        )}
                        {hasUrl && (
                          <a href={safeUrl(evt.source_url)} target="_blank" rel="noopener noreferrer"
                            onClick={e => e.stopPropagation()}
                            style={{ color: lc, textDecoration: "none", marginLeft: "auto" }}>↗ SOURCE</a>
                        )}
                        {satUrl && (
                          <a href={satUrl} target="_blank" rel="noopener noreferrer"
                            onClick={e => e.stopPropagation()}
                            style={{ color: "#58a6ff", textDecoration: "none", fontSize: 11 }}
                            title="Google Maps imagery: verify capture date and resolution with the provider">
                            🗺 GOOGLE MAPS
                          </a>
                        )}
                        {copUrl && (
                          <a href={copUrl} target="_blank" rel="noopener noreferrer"
                            onClick={e => e.stopPropagation()}
                            style={{ color: "#7ee787", textDecoration: "none", fontSize: 11 }}
                            title="NASA Worldview: VIIRS thermal anomaly overlay for this date">
                            🛰 WORLDVIEW
                          </a>
                        )}
                        {imagery.copernicus&&<a href={imagery.copernicus} target="_blank" rel="noopener noreferrer" onClick={e=>e.stopPropagation()} style={{color:"#d29922",textDecoration:"none",fontSize:11}} title="Copernicus browser: inspect provider coverage and acquisition dates">COP BROWSER</a>}
                        {satUrl && sentinelHubInstanceId && (() => {
                          // Sentinel Hub WMS thumbnail — direct JPEG from orbital sensor
                          const time=Date.parse(evt.timestamp);if(!Number.isFinite(time))return null;
                          const d = new Date(time);
                          const from = new Date(d.getTime() - 30 * 86400000).toISOString().split("T")[0];  // 30-day lookback
                          const to   = d.toISOString().split("T")[0];
                          const pad  = 0.04; // ~4km box
                          const bbox = `${(evt.lon!-pad).toFixed(4)},${(evt.lat!-pad).toFixed(4)},${(evt.lon!+pad).toFixed(4)},${(evt.lat!+pad).toFixed(4)}`;
                          const thumbUrl = `https://sh.dataspace.copernicus.eu/ogc/wms/${sentinelHubInstanceId}?SERVICE=WMS&REQUEST=GetMap&LAYERS=TRUE_COLOR&BBOX=${bbox}&CRS=EPSG:4326&WIDTH=300&HEIGHT=240&FORMAT=image/jpeg&TIME=${from}/${to}`;
                          return (
                            <a href={thumbUrl} target="_blank" rel="noopener noreferrer"
                              onClick={e => e.stopPropagation()}
                              style={{ color: "#7ee787", textDecoration: "none", fontSize: 11 }}
                              title="Load Sentinel Hub live WMS thumbnail for this location">
                              🛰 WMS THUMB
                            </a>
                          );
                        })()}
                      </div>
                    </div>
                    <span style={{ fontSize: 11, color: "#a3b9ca", whiteSpace: "nowrap", alignSelf: "start" }}>
                      {evt.timestamp ? timeAgo(evt.timestamp) : ""}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

      </div>

      {/* ── INTEL BRIEF MODAL ──────────────────────────────────────────── */}
      {showIntelBrief && sitrep && (
        <div
          onClick={() => setShowIntelBrief(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 9999,
            background: "rgba(0,0,0,0.85)",
            display: "flex", alignItems: "center", justifyContent: "center",
            backdropFilter: "blur(4px)",
            padding: "24px",
          }}
        >
          <div ref={modalRef} role="dialog" aria-modal="true" aria-labelledby="expanded-brief-title" tabIndex={-1}
            onClick={e => e.stopPropagation()}
            style={{
              background: "#080e1a",
              border: `1px solid ${lc}44`,
              borderRadius: 6,
              width: "min(860px, 96vw)",
              maxHeight: "90vh",
              display: "flex", flexDirection: "column",
              boxShadow: `0 0 60px ${lc}18, 0 24px 80px rgba(0,0,0,0.8)`,
              overflow: "hidden",
            }}
          >
            {/* Modal header */}
            <div style={{
              display: "flex", alignItems: "center", gap: 12,
              padding: "14px 20px",
              background: `linear-gradient(90deg, ${lc}18 0%, rgba(8,14,26,0.95) 70%)`,
              borderBottom: `2px solid ${lc}44`,
              flexShrink: 0,
            }}>
              <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: 3, color: lc }}>◈</span>
              <div>
                <h2 id="expanded-brief-title" style={{fontSize:12,fontWeight:800,letterSpacing:2.5,color:"#e6edf3"}}>{isSourceDigest(sitrep)?"SOURCE BRIEFING":"INTEL BRIEF"}</h2>
                <div style={{ fontSize: 11, color: lc, letterSpacing: 1.5, marginTop: 1 }}>
                  SITREP #{sitrep.id} · {sitrep.escalation_level} · INDEX {briefIndexLabel(sitrep)} · {fmtDate(sitrep.generated_at)}
                </div>
              </div>
              <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
                {sitrep.events_analyzed && (
                  <span style={{ fontSize: 11, color: "#8da3b7", fontFamily: mono }}>
                    {sitrep.events_analyzed} REPORTS {isSourceDigest(sitrep)?"COMPILED":"ANALYZED"}
                  </span>
                )}
                <button data-modal-close aria-label="Close expanded briefing"
                  onClick={() => setShowIntelBrief(false)}
                  style={{
                    background: "rgba(248,81,73,0.12)", border: "1px solid rgba(248,81,73,0.3)",
                    borderRadius: 3, color: "#f85149", fontSize: 12, width: 28, height: 28,
                    cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                    fontFamily: mono,
                  }}
                >✕</button>
              </div>
            </div>

            {/* Modal body — scrollable */}
            <div role="region" aria-label="Expanded briefing content" tabIndex={0} style={{ flex: 1, overflowY: "auto", padding: "24px 28px",
              display: "flex", flexDirection: "column", gap: 22,
              scrollbarWidth: "thin", scrollbarColor: `${lc}33 transparent`,
            }}>
              {/* Headline */}
              <div style={{
                borderLeft: `4px solid ${lc}`,
                paddingLeft: 16, paddingTop: 4, paddingBottom: 4,
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: lc, letterSpacing: 2, marginBottom: 8 }}>
                  HEADLINE
                </div>
                <div style={{ fontSize: 18, fontWeight: 700, color: "#e6edf3", lineHeight: 1.5,
                  fontFamily: "var(--font-sans, system-ui)" }}>
                  {sitrep.headline}
                </div>
              </div>

              {/* Situation Assessment */}
              {sitrep.situation && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#a3b9ca",
                    letterSpacing: 2, display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 20, height: 1, background: "#1a2a3a", display: "inline-block" }} />
                    ◉ SITUATION ASSESSMENT
                    <span style={{ flex: 1, height: 1, background: "#1a2a3a", display: "inline-block" }} />
                  </div>
                  <div style={{ fontSize: 12, color: "#8a9ab5", lineHeight: 1.9,
                    fontFamily: "var(--font-sans, system-ui)",
                    background: "rgba(10,20,35,0.6)", border: "1px solid #1a2a3a",
                    borderRadius: 4, padding: "14px 16px" }}>
                    {parseRefs(sitrep.situation)}
                  </div>
                </div>
              )}

              {/* Intel sections — full readable paragraphs in modal */}
              {intelSections.map(s => (
                <div key={s.label} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: s.color,
                    letterSpacing: 2, display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 12 }}>{s.icon}</span>
                    <span>{s.label}</span>
                    <span style={{ flex: 1, height: 1, background: `${s.color}33`, display: "inline-block" }} />
                  </div>
                  <div style={{
                    fontSize: 12, color: "#8a9ab5", lineHeight: 1.9,
                    fontFamily: "var(--font-sans, system-ui)",
                    borderLeft: `3px solid ${s.color}66`,
                    paddingLeft: 16,
                  }}>
                    {parseRefs(s.text)}
                  </div>
                </div>
              ))}

              {/* Key Questions */}
              {(() => {
                let kqs: {q: string; a: string; watch: string}[] = [];
                try {
                  const raw = sitrep.key_questions;
                  if (Array.isArray(raw)) kqs = raw;
                  else if (typeof raw === "string" && raw.length > 2) kqs = JSON.parse(raw);
                } catch (_) {}
                if (!kqs.length) return null;
                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#58a6ff",
                      letterSpacing: 2, display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 12 }}>◈</span>
                      <span>INTELLIGENCE FOCUS</span>
                      <span style={{ flex: 1, height: 1, background: "rgba(88,166,255,0.2)", display: "inline-block" }} />
                    </div>
                    {kqs.map((kq, i) => (
                      <div key={i} style={{
                        borderLeft: "3px solid rgba(88,166,255,0.3)", paddingLeft: 16,
                        display: "flex", flexDirection: "column", gap: 6,
                      }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "#c9d1d9", lineHeight: 1.4,
                          fontFamily: "var(--font-sans, system-ui)" }}>
                          {i + 1}. {kq.q}
                        </div>
                        <div style={{ fontSize: 12, color: "#7a9ab5", lineHeight: 1.8,
                          fontFamily: "var(--font-sans, system-ui)" }}>
                          {parseRefs(kq.a)}
                        </div>
                        {kq.watch && (
                          <div style={{ display: "flex", gap: 8, alignItems: "flex-start",
                            background: "rgba(240,136,62,0.06)", borderRadius: 3,
                            padding: "6px 10px", marginTop: 2 }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: "#f0883e",
                              letterSpacing: 1.5, whiteSpace: "nowrap", marginTop: 2 }}>WATCH FOR:</span>
                            <span style={{ fontSize: 12, color: "#f0883e", opacity: 0.85, lineHeight: 1.6,
                              fontFamily: "var(--font-sans, system-ui)" }}>{kq.watch}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                );
              })()}

              {/* Footer */}
              <div style={{
                borderTop: "1px solid #1a2a3a", paddingTop: 16,
                display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center",
              }}>
                {[
                  ["GENERATED", fmtDate(sitrep.generated_at)],
                  ["SITREP ID", `#${sitrep.id}`],
                  [isSourceDigest(sitrep)?"REPORTS COMPILED":"REPORTS ANALYZED", `${sitrep.events_analyzed}`],
                  ["ESCALATION INDEX", `${briefIndexLabel(sitrep)}`],
                ].map(([k, v]) => (
                  <div key={k} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span style={{ fontSize: 11, color: "#a3b9ca", letterSpacing: 1, fontFamily: mono }}>{k}:</span>
                    <span style={{ fontSize: 11, color: "#a3b9ca", fontFamily: mono }}>{v}</span>
                  </div>
                ))}
                <div style={{ marginLeft: "auto" }}>
                  <button onClick={() => setShowIntelBrief(false)} style={{
                    background: "none", border: "1px solid #1a2a3a",
                    borderRadius: 3, color: "#8da3b7", fontSize: 11,
                    padding: "4px 12px", cursor: "pointer", fontFamily: mono, letterSpacing: 1,
                  }}>CLOSE</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* VIDEO MODAL */}
      {videoModalUrl && (
        <div onClick={() => setVideoModalUrl(null)} style={{
          position: "fixed", inset: 0, zIndex: 9999,
          background: "rgba(0,0,0,0.88)", display: "flex",
          alignItems: "center", justifyContent: "center",
        }}>
          <div ref={modalRef} role="dialog" aria-modal="true" aria-label="Recorded briefing video playback" tabIndex={-1} onClick={e => e.stopPropagation()} style={{
            width: "min(900px, 94vw)", display: "flex", flexDirection: "column",
            background: "#030508", border: "1px solid #1a2a3a", borderRadius: 4,
            overflow: "hidden", boxShadow: "0 0 60px rgba(0,0,0,0.9)",
          }}>
            <div style={{ display: "flex", alignItems: "center", padding: "8px 14px",
              borderBottom: "1px solid #1a2a3a", background: "#040810" }}>
              <span style={{ fontFamily: mono, fontSize: 11, fontWeight: 700,
                letterSpacing: 1.5, color: lc }}>SITREP VIDEO PLAYBACK</span>
              <span style={{ fontFamily: mono, fontSize: 11, color: "#8da3b7",
                marginLeft: 12 }}>{(videoModalUrl.split("/").pop() || "").split("?")[0]}</span>
              <button data-modal-close onClick={() => setVideoModalUrl(null)} style={{
                marginLeft: "auto", background: "rgba(248,81,73,0.15)",
                border: "1px solid rgba(248,81,73,0.4)", borderRadius: 3,
                color: "#f85149", fontFamily: mono, fontSize: 11, padding: "3px 10px",
                cursor: "pointer", fontWeight: 700,
              }}>X CLOSE</button>
            </div>
            <video controls autoPlay preload="auto"
              style={{ width: "100%", maxHeight: "70vh", background: "#000", display: "block" }}>
              <source src={videoModalUrl} type="video/mp4" />
            </video>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const { events, isConnected, loadFullHistory, historyStatus, recoveryStatus, historyTruncated, historyStart } = useEventStream();
  const [replayCursor, setReplayCursor] = useState<number | null>(null);
  const [activeRange, setActiveRange] = useState<{ start: Date; end: Date } | null>(
    () => ({ start: new Date(nowMs() - 24 * 3600000), end: new Date(nowMs()) })
  );
  const { aircraft, jammingZones, vessels,loadingSnapshots,snapshotAt } = useTracking({
    replayCursor,
    replayWindow: replayCursor != null && activeRange ? {
      start: activeRange.start.getTime(), end: activeRange.end.getTime(),
    } : null,
  });
  const [demoMode, setDemoMode] = useState(SHOWCASE);
  const [collectionState,setCollectionState]=useState("Connecting to backend…");
  const [escalationLevel, setEscalationLevel] = useState<"STABLE"|"ELEVATED"|"ESCALATING"|"CRITICAL"|"UNASSESSED">("UNASSESSED");
  const [firmsHotspots, setFirmsHotspots] = useState<Array<{ lat: number; lon: number; frp: number; conf: number | null; confidence_label?: string; synthetic?: boolean; ts: string; google_maps_url: string; copernicus_url: string; wms_thumbnail: string; gibs_viirs_thumb: string; gibs_modis_thumb: string; gibs_landsat_thumb: string; eo_browser_url: string; landsatlook_url: string; planet_url: string; probable_flare: boolean; flare_zone: string; matched: boolean }>>([]);
  const [activeSources, setActiveSources] = useState<Set<string>>(
    () => new Set(["telegram", "x", "rss", "sensor", "other"])
  );
  const toggleSource = (src: string) => {
    setActiveSources(prev => {
      const next = new Set(prev);
      if (next.has(src)) { if (next.size > 1) next.delete(src); } else { next.add(src); }
      return next;
    });
  };
  const { isMobile, isLandscape,isOverlay } = useIsMobile();
  const [showFeed, setShowFeed] = useState(false);
  useEffect(()=>{
    if(showFeed&&(!isMobile||isLandscape)){
      setShowFeed(false);
      // Rotation replaces the sheet with the landscape feed. Do not reopen an
      // old modal when the user rotates back, or strand its former focus.
      if(document.activeElement===document.body)document.querySelector<HTMLButtonElement>('.mobile-bottom-nav button[aria-pressed="true"]')?.focus();
    }
  },[showFeed,isMobile,isLandscape]);
  const [earthFocused, setEarthFocused] = useState(false);
  const [viewMode, setViewModeState] = useState<ViewMode>(() => {
    const view = new URLSearchParams(window.location.search).get("view");
    return workspaceView(view);
  });
  const setViewMode = useCallback((view: ViewMode) => {setViewModeState(view);const url=new URL(window.location.href);url.searchParams.set("view",view);window.history.replaceState(null,"",url);},[]);
  const {panelRef,stageRef}=useWorkspacePanelFocus(viewMode,()=>setViewMode("earth"));
  const [showSettings,setShowSettings]=useState(false);
  const [operatorKey,setOperatorKey]=useState("");
  const [briefDesk,setBriefDesk]=useState<"sources"|"analysis">("sources");
  const [mediaDesk,setMediaDesk]=useState<"sources"|"video">("sources");
  const {googleKey,googleEnabled,applyManual:applyEarthProvider,applyServerConfig:applyEarthConfig}=useEarthProvider();
  // Open on the actual workspace. Methods remain one click away in the header.
  const [showAbout, setShowAbout] = useState(false);
  const [focusEventId, setFocusEventId] = useState<number | null>(null);
  const focusTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleFeedEventClick = useCallback((evt: import("./types/event").ConflictEvent) => {
    if(viewMode!=="earth")setViewMode("earth");
    setFocusEventId(null);
    if (focusTimeoutRef.current) clearTimeout(focusTimeoutRef.current);
    focusTimeoutRef.current = setTimeout(() => setFocusEventId(evt.id), 30);
  }, [viewMode]);
  useEffect(()=>()=>{if(focusTimeoutRef.current)clearTimeout(focusTimeoutRef.current);},[]);
  const [timeRange, setTimeRange] = useState<{ earliest: Date; latest: Date } | null>(null);

  useEffect(() => {
    const controller=new AbortController();
    apiFetch(`${API_BASE}/config`,{signal:controller.signal}).then(r => {if(!r.ok)throw new Error();return r.json();}).then(d => {
      if(controller.signal.aborted)return;
      setDemoMode(!!d.demo_mode);
      setCollectionState(d.live_ingestion_enabled ? "Collection enabled · individual source freshness requires verification" : "Collection disabled · enable configured sources to collect live reports");
      applyEarthConfig(d);
    }).catch(() => {if(!controller.signal.aborted)setCollectionState("Backend unavailable · displayed data may be stale");});
    return()=>controller.abort();
  }, [applyEarthConfig]);

  // Fetch NASA FIRMS thermal hotspots for satellite layer (refresh every 3h)
  useEffect(() => {
    const fetchHotspots = () => {
      apiFetch(`${API_BASE}/satellite/hotspots`)
        .then(r => r.json())
        .then(d => {
          if (Array.isArray(d.hotspots)) {
            setFirmsHotspots(d.hotspots);
          }
        })
        .catch(() => {});
    };
    fetchHotspots();
    const interval = setInterval(fetchHotspots, 3 * 60 * 60 * 1000); // 3h
    return () => clearInterval(interval);
  }, []);
  useEffect(() => {
    const fetchRange = () => {
      apiFetch(`${API_BASE}/events/time-range`).then(r => r.json())
        .then(d => { if (d.earliest && d.latest)
          setTimeRange({ earliest: new Date(d.earliest), latest: new Date(d.latest) }); })
        .catch(() => {});
    };
    fetchRange();
    const interval = setInterval(fetchRange, 30000);
    return () => clearInterval(interval);
  }, []);

  const filteredEvents = useMemo(() => {
    const start = activeRange?.start.getTime()??-Infinity;
    const end = activeRange?.end.getTime()??Infinity;
    const cutoff = replayCursor ?? end;
    return events.filter(e => {
      const t = new Date(e.timestamp).getTime();
      if ((activeRange||replayCursor!==null)&&(!Number.isFinite(t)||t < start || t > cutoff)) return false;
      return activeSources.has(reportSourceKind(e));
    });
  }, [events, activeRange, replayCursor, activeSources]);

  const onRangeChange = useCallback((range: { start: Date; end: Date } | null) => {
    setActiveRange(range);
  }, []);

  return (
    <>
      {SHOWCASE ? <ShowcaseBar view={viewMode} onView={setViewMode} /> : <div className="runtime-banner" role="status"><SourceStatus fallback={collectionState}/><a href="?showcase=true">Explore synthetic showcase ↗</a></div>}
      <main aria-label="Conflict monitoring workspace" className={`${SHOWCASE ? "app-grid has-showcase" : "app-grid has-runtime"}${viewMode!=="earth"?" has-workspace-panel":""}${earthFocused&&viewMode==="earth"?" earth-focused":""}`}>
        <Header
          isConnected={isConnected} eventCount={filteredEvents.length}
          aircraftCount={aircraft.length} vesselCount={vessels.length}
          demoMode={demoMode}
          escalationLevel={escalationLevel} onAboutClick={() => setShowAbout(true)} onSettingsClick={() => setShowSettings(true)}
          viewMode={viewMode} onViewModeChange={setViewMode}
          activeSources={activeSources} onSourceToggle={toggleSource}
          earthFocused={earthFocused} onEarthFocusChange={()=>setEarthFocused(value=>!value)}
        />
        <div className="market-strip-wrap"><MarketStrip /></div>
        <div ref={stageRef} inert={viewMode!=="earth"&&isOverlay} aria-hidden={viewMode!=="earth"&&isOverlay?true:undefined} className="earth-stage" style={{gridArea:"map",minWidth:0,minHeight:0,overflow:"hidden"}}>
          <Suspense fallback={<div className="earth-loading" role="status">Loading Earth workspace…</div>}>
            <CesiumView focusEventId={focusEventId} googleKey={googleKey} googleEnabled={googleEnabled} onConfigure={()=>setShowSettings(true)} events={filteredEvents} aircraft={aircraft} vessels={vessels} jammingZones={jammingZones} firmsHotspots={firmsHotspots} replayCursor={replayCursor} windowStart={activeRange?.start.getTime()} loadingSnapshots={loadingSnapshots} snapshotAt={snapshotAt}/>
          </Suspense>
        </div>
        {viewMode!=="earth"&&<aside ref={panelRef} className="workspace-panel" aria-label={viewMode==="media"?"Media workspace panel":"Brief workspace panel"}>
          <div className="workspace-panel-header"><div><span>EARTH WORKSPACE</span><h2>{viewMode==="media"?"Media desk":"Source briefing"}</h2></div><button data-panel-close onClick={()=>setViewMode("earth")} aria-label="Back to Earth — close workspace panel">Back to Earth <span aria-hidden="true">×</span></button></div>
          <div className="workspace-subnav" role="group" aria-label={viewMode==="media"?"Media tools":"Briefing tools"}>
            {viewMode==="media"?<><button aria-pressed={mediaDesk==="sources"} onClick={()=>setMediaDesk("sources")}>Sources &amp; broadcasts</button><button aria-pressed={mediaDesk==="video"} onClick={()=>setMediaDesk("video")}>Narrated briefing</button></>:<><button aria-pressed={briefDesk==="sources"} onClick={()=>setBriefDesk("sources")}>Source briefing</button><button aria-pressed={briefDesk==="analysis"} onClick={()=>setBriefDesk("analysis")}>Local analysis</button></>}
          </div>
          <div className="workspace-panel-body">
            {viewMode==="media"?(mediaDesk==="video"?<LocalBriefingPanel mode="video" operatorKey={operatorKey} onConfigureOperator={()=>setShowSettings(true)}/>:<Suspense fallback={<div role="status">Loading media desk…</div>}><IntelMediaView events={filteredEvents}/></Suspense>):briefDesk==="analysis"?<LocalBriefingPanel mode="analysis" operatorKey={operatorKey} onConfigureOperator={()=>setShowSettings(true)}/>:<SitrepBroadcastView style={{width:"100%",height:"100%",minHeight:0}}/>}
          </div>
        </aside>}
        {viewMode==="earth"&&(!isMobile||isLandscape)&&<div className="sidebar"><div className="sidebar-feed"><LiveFeed selectedEventId={focusEventId} events={filteredEvents} allEvents={events} onEventClick={handleFeedEventClick}/></div></div>}

        <div className="timeline-wrap" style={{ gridArea: "timeline" }}>
          <TimelineScrubber
            allEvents={events} timeRange={timeRange} activeRange={activeRange}
            onRangeChange={onRangeChange} onLoadHistory={loadFullHistory}
            historyStatus={historyStatus} recoveryStatus={recoveryStatus} historyTruncated={historyTruncated} historyStart={historyStart}
            replayCursor={replayCursor} onReplayCursorChange={setReplayCursor}
          />
        </div>

      </main>

      {/* Mobile bottom nav */}
      {isMobile && (
        <MobileNav viewMode={viewMode} onViewModeChange={setViewMode}
          onOpenFeed={isLandscape?undefined:()=>setShowFeed(true)} reportCount={filteredEvents.length} />
      )}

      {/* Slide-up feed sheet — portrait mobile */}
      {isMobile && !isLandscape && showFeed && (
        <FeedSheet onClose={() => setShowFeed(false)}>
          <LiveFeed selectedEventId={focusEventId} events={filteredEvents} allEvents={events} onEventClick={(evt) => {
            handleFeedEventClick(evt);
            setShowFeed(false);
          }} />
        </FeedSheet>
      )}

      {showSettings && <SettingsPanel operatorKey={operatorKey} onOperatorKeyChange={setOperatorKey} googleKey={googleKey} googleEnabled={googleEnabled} onApply={(key,enabled)=>{applyEarthProvider(key,enabled);setShowSettings(false);}} onClose={()=>setShowSettings(false)} />}
      {showAbout && <AboutPanel onClose={() => setShowAbout(false)} />}
    </>
  );
}
