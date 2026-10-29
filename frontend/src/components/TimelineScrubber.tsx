import { SHOWCASE } from "../lib/runtime";
import { nowMs } from "../lib/clock";
import { MAX_LOADED_REPORTS, type HistoryStatus } from "../lib/history";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ConflictEvent } from "../types/event";

const EVENT_COLORS: Record<string, string> = {
  military:   "#f85149",
  diplomatic: "#58a6ff",
  economic:   "#d29922",
  cyber:      "#bc8cff",
};

// Conflict start — left edge of the entire timeline
const DEFAULT_HISTORY_START = new Date(SHOWCASE ? nowMs() - 24 * 3600000 : ((import.meta as any).env?.VITE_HISTORY_START || "2026-02-28T00:00:00Z"));

function utcDayStart(d: Date): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
}

function formatDayLabel(d: Date): string {
  const months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
  return `${String(d.getUTCDate()).padStart(2,"0")} ${months[d.getUTCMonth()]}`;
}

function formatTimeLabel(d: Date): string {
  const months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
  return `${String(d.getUTCDate()).padStart(2,"0")} ${months[d.getUTCMonth()]} ${String(d.getUTCHours()).padStart(2,"0")}:${String(d.getUTCMinutes()).padStart(2,"0")} UTC`;
}

function formatDuration(ms: number): string {
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `${days}d`;
}

function conflictDay(d: Date, start: Date): number {
  return Math.floor((d.getTime() - start.getTime()) / 86400000) + 1;
}

/** Keep the full history domain, but budget axis labels by actual available width. */
export function dayAxisTicks(rangeStart:number,rangeEnd:number,width:number){
  if(!Number.isFinite(rangeStart)||!Number.isFinite(rangeEnd)||rangeEnd<rangeStart)return [];
  const day=86400000,span=Math.max(rangeEnd-rangeStart,60000);
  let first=utcDayStart(new Date(rangeStart)).getTime();
  if(first<rangeStart)first+=day;
  const days=Math.floor((rangeEnd-first)/day)+1;
  const budget=Math.max(1,Math.min(24,Math.floor((Number.isFinite(width)?width:1)/64)));
  const required=Math.max(1,Math.ceil(days/budget));
  const stride=[1,2,3,7,14,30,60,90,180,365].find(value=>value>=required)??Math.ceil(required/365)*365;
  const ticks:Array<{pct:number;dayNum:number;ts:number}>=[];
  for(let ts=first;ts<=rangeEnd;ts+=stride*day){
    ticks.push({pct:((ts-rangeStart)/span)*100,dayNum:conflictDay(new Date(ts),new Date(rangeStart)),ts});
  }
  return ticks;
}

// ── Preset definitions ──────────────────────────────────────────────────────
interface Preset {
  label: string;
  ms: number | "all";   // ms = duration back from now; "all" = from conflict start
  live: boolean;        // if true, window auto-follows "now" every 30s
}

const PRESETS: Preset[] = [
  { label: "1H",  ms: 1  * 3600000,  live: true  },
  { label: "2H",  ms: 2  * 3600000,  live: true  },
  { label: "6H",  ms: 6  * 3600000,  live: true  },
  { label: "12H", ms: 12 * 3600000,  live: true  },
  { label: "24H", ms: 24 * 3600000,  live: true  },
  { label: "48H", ms: 48 * 3600000,  live: true  },
  { label: "7D",  ms: 7  * 86400000, live: false },
  { label: "ALL", ms: "all",          live: false },
];

function makeRangeForPreset(p: Preset, start: Date): { start: Date; end: Date } {
  const now = nowMs();
  if (p.ms === "all") return { start, end: new Date(now) };
  return { start: new Date(now - (p.ms as number)), end: new Date(now) };
}

// ── Replay speed options ───────────────────────────────────────────────────
// These are "how many seconds of conflict time per 1 second of real time"
// At 60x, 1 real second = 1 conflict minute. At 3600x, 1 real second = 1 conflict hour.
const REPLAY_SPEEDS = [60, 300, 600, 1800, 3600] as const;
const REPLAY_SPEED_LABELS: Record<number, string> = {
  60: "1m/s", 300: "5m/s", 600: "10m/s", 1800: "30m/s", 3600: "1h/s",
};
type ReplaySpeed = typeof REPLAY_SPEEDS[number];

interface TimelineScrubberProps {
  allEvents:     ConflictEvent[];
  timeRange:     { earliest: Date; latest: Date } | null;
  activeRange:   { start: Date; end: Date } | null;
  onRangeChange: (range: { start: Date; end: Date } | null) => void;
  onLoadHistory?: () => void;
  historyStatus?: HistoryStatus;
  recoveryStatus?: HistoryStatus;
  historyTruncated?: boolean;
  historyStart?: string;
  replayCursor?: number | null;
  onReplayCursorChange?: (cursor: number | null) => void;
}

export function TimelineScrubber({
  allEvents, timeRange, activeRange, onRangeChange,
  onLoadHistory, replayCursor, onReplayCursorChange, historyStatus="idle", recoveryStatus="idle", historyTruncated=false, historyStart,
}: TimelineScrubberProps) {
  const conflictStart=useMemo(()=>{
    const value=historyStart?new Date(historyStart):DEFAULT_HISTORY_START;
    return Number.isFinite(value.getTime())?value:new Date("2026-02-28T00:00:00Z");
  },[historyStart]);
  const trackRef   = useRef<HTMLDivElement>(null);
  const [axisWidth,setAxisWidth]=useState(1024);
  const [isDragging, setIsDragging]     = useState<"left" | "right" | "window" | null>(null);
  const [activePreset, setActivePreset] = useState<string>("24H");
  const liveTickRef  = useRef<number | null>(null);
  const dragStartRef = useRef({ x: 0, startMs: 0, endMs: 0 });

  // ── Replay state ──────────────────────────────────────────────────────────
  const [isPlaying, setIsPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState<ReplaySpeed>(600);
  const replayRef = useRef<number | null>(null);
  const cursorRef = useRef<number>(0); // internal cursor tracked by ref to avoid re-render loops
  const speedRef = useRef<number>(600); // ref mirror of replaySpeed for interval access
  speedRef.current = replaySpeed;
  const REPLAY_TICK_MS = 50; // 20 fps update rate

  const rangeStart = conflictStart.getTime();
  const rangeEnd   = Math.max(timeRange?.latest?.getTime() ?? nowMs(), nowMs());
  const fullSpan   = Math.max(rangeEnd - rangeStart, 60000);

  const winStart = activeRange?.start?.getTime() ?? nowMs() - 24 * 3600000;
  const winEnd   = activeRange?.end?.getTime()   ?? nowMs();

  const leftPct  = Math.max(0, ((winStart - rangeStart) / fullSpan) * 100);
  const widthPct = Math.max(0.5, ((winEnd - winStart) / fullSpan) * 100);

  useEffect(()=>{
    const track=trackRef.current;if(!track)return;
    const measure=()=>{const width=track.getBoundingClientRect().width;if(width>0)setAxisWidth(width);};
    measure();
    if(typeof ResizeObserver!=="undefined"){
      const observer=new ResizeObserver(measure);observer.observe(track);return()=>observer.disconnect();
    }
    window.addEventListener("resize",measure);return()=>window.removeEventListener("resize",measure);
  },[]);

  // ── Auto-follow live presets ───────────────────────────────────────────────
  useEffect(() => {
    const preset = PRESETS.find((p) => p.label === activePreset);
    if (!preset?.live) {
      if (liveTickRef.current) { clearInterval(liveTickRef.current); liveTickRef.current = null; }
      return;
    }
    liveTickRef.current = window.setInterval(() => {
      onRangeChange(makeRangeForPreset(preset,conflictStart));
    }, 30000);
    return () => { if (liveTickRef.current) clearInterval(liveTickRef.current); };
  }, [activePreset, onRangeChange, conflictStart]);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.code === "ArrowLeft" && activeRange) {
        e.preventDefault();
        const step = Math.max(3600000, (winEnd - winStart) * 0.15);
        setActivePreset("");
        onRangeChange({ start: new Date(Math.max(rangeStart, winStart - step)), end: new Date(Math.max(rangeStart + (winEnd - winStart), winEnd - step)) });
      } else if (e.code === "ArrowRight" && activeRange) {
        e.preventDefault();
        const step = Math.max(3600000, (winEnd - winStart) * 0.15);
        const shift = Math.max(0, Math.min(step, nowMs() - winEnd));
        setActivePreset("");
        onRangeChange({ start: new Date(winStart + shift), end: new Date(winEnd + shift) });
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeRange, winStart, winEnd, onRangeChange, rangeStart]);

  // ── Replay engine ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!isPlaying || !onReplayCursorChange) {
      if (replayRef.current) { clearInterval(replayRef.current); replayRef.current = null; }
      return;
    }

    replayRef.current = window.setInterval(() => {
      // speedRef.current gives us latest speed without needing it in the dep array
      const advanceMs = speedRef.current * (REPLAY_TICK_MS / 1000) * 1000;
      cursorRef.current += advanceMs;
      if (cursorRef.current >= winEnd) {
        cursorRef.current = winEnd;
        setIsPlaying(false);
        onReplayCursorChange(winEnd);
        return;
      }
      onReplayCursorChange(cursorRef.current);
    }, REPLAY_TICK_MS);

    return () => { if (replayRef.current) { clearInterval(replayRef.current); replayRef.current = null; } };
  }, [isPlaying, winEnd, onReplayCursorChange]);

  const handlePlayPause = useCallback(() => {
    if (isPlaying) {
      setIsPlaying(false);
    } else {
      const resume=replayCursor!=null&&replayCursor>=winStart&&replayCursor<winEnd?replayCursor:winStart;
      cursorRef.current = resume;
      onReplayCursorChange?.(resume);
      setIsPlaying(true);
      setActivePreset("");
    }
  }, [isPlaying, winStart, winEnd, replayCursor, onReplayCursorChange]);

  const handleSpeedChange = useCallback(() => {
    const idx = REPLAY_SPEEDS.indexOf(replaySpeed);
    const next = REPLAY_SPEEDS[(idx + 1) % REPLAY_SPEEDS.length];
    setReplaySpeed(next);
  }, [replaySpeed]);

  // ── Day axis labels ───────────────────────────────────────────────────────
  const dayLabels = useMemo(()=>dayAxisTicks(rangeStart,rangeEnd,axisWidth),[rangeStart,rangeEnd,axisWidth]);

  // ── Density histogram ─────────────────────────────────────────────────────
  const densityBuckets = useMemo(() => {
    const buckets: Map<number, { total: number; military: number }> = new Map();
    let cur = utcDayStart(conflictStart).getTime();
    while (cur <= rangeEnd) { buckets.set(cur, { total: 0, military: 0 }); cur += 86400000; }
    for (const ev of allEvents) {
      const t = new Date(ev.timestamp).getTime();
      if (t < rangeStart || t > rangeEnd) continue;
      const bucket = utcDayStart(new Date(t)).getTime();
      const b = buckets.get(bucket);
      if (b) { b.total++; if (ev.event_type === "military") b.military++; }
    }
    const maxCount = Math.max(1, ...Array.from(buckets.values()).map((b) => b.total));
    return Array.from(buckets.entries()).map(([ts, b]) => ({
      pct: ((ts - rangeStart) / fullSpan) * 100,
      widthPct: (86400000 / fullSpan) * 100,
      heightFrac: b.total / maxCount,
      military: b.military,
      total: b.total,
      ts,
    })).filter((b) => b.pct >= 0 && b.pct <= 100);
  }, [allEvents, rangeStart, rangeEnd, fullSpan]);

  // ── Event ticks ───────────────────────────────────────────────────────────
  const ticks = useMemo(() =>
    allEvents
      .filter((e) => e.lat != null && e.lon != null)
      .map((e) => {
        const t = new Date(e.timestamp).getTime();
        const pct = ((t - rangeStart) / fullSpan) * 100;
        return { pct, severity: e.severity, type: e.event_type };
      })
      .filter((t) => t.pct >= 0 && t.pct <= 100),
    [allEvents, rangeStart, fullSpan],
  );

  // ── Drag handling ─────────────────────────────────────────────────────────
  const getTimeFromX = useCallback((clientX: number): number => {
    if (!trackRef.current) return 0;
    const rect = trackRef.current.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return rangeStart + pct * fullSpan;
  }, [rangeStart, fullSpan]);

  const onMouseDown = useCallback((e: React.MouseEvent, target: "left" | "right" | "window") => {
    e.preventDefault(); e.stopPropagation();
    setIsDragging(target);
    setActivePreset(""); // custom drag — clear preset indicator
    dragStartRef.current = { x: e.clientX, startMs: winStart, endMs: winEnd };
  }, [winStart, winEnd]);

  useEffect(() => {
    if (!isDragging) return;
    const onMove = (e: MouseEvent) => {
      const { x: startX, startMs, endMs } = dragStartRef.current;
      const dx = e.clientX - startX;
      const trackWidth = trackRef.current?.getBoundingClientRect().width ?? 1;
      const dtMs = (dx / trackWidth) * fullSpan;
      if (isDragging === "window") {
        let ns = startMs + dtMs; let ne = endMs + dtMs;
        if (ns < rangeStart) { ne += rangeStart - ns; ns = rangeStart; }
        if (ne > nowMs()) { ns -= ne - nowMs(); ne = nowMs(); }
        onRangeChange({ start: new Date(ns), end: new Date(ne) });
      } else if (isDragging === "left") {
        const ns = Math.max(rangeStart, Math.min(endMs - 3600000, startMs + dtMs));
        onRangeChange({ start: new Date(ns), end: new Date(endMs) });
      } else {
        const ne = Math.min(nowMs(), Math.max(startMs + 3600000, endMs + dtMs));
        onRangeChange({ start: new Date(startMs), end: new Date(ne) });
      }
    };
    const onUp = () => setIsDragging(null);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, [isDragging, fullSpan, rangeStart, onRangeChange]);

  const onTrackClick = useCallback((e: React.MouseEvent) => {
    if (isDragging) return;
    const clickTime = getTimeFromX(e.clientX);
    const halfWindow = (winEnd - winStart) / 2;
    const newStart = Math.max(rangeStart, clickTime - halfWindow);
    const newEnd   = Math.min(nowMs(), clickTime + halfWindow);
    setActivePreset("");
    onRangeChange({ start: new Date(newStart), end: new Date(newEnd) });
  }, [getTimeFromX, winStart, winEnd, rangeStart, isDragging, onRangeChange]);

  // ── Derived stats ─────────────────────────────────────────────────────────
  const geoEvents    = allEvents.filter((e) => e.lat != null && e.lon != null);
  const windowEvents = allEvents.filter((e) => {
    const t = new Date(e.timestamp).getTime();
    return t >= winStart && t <= winEnd && e.lat != null && e.lon != null;
  });
  const currentDay  = conflictDay(new Date(nowMs()),conflictStart);
  const windowSpan  = winEnd - winStart;
  const isLivePreset = !!(activePreset && PRESETS.find((p) => p.label === activePreset)?.live);

  return (
    <div className="timeline-scrubber" style={{
      gridArea: "timeline",
      background: "#06090f",
      borderTop: "1px solid rgba(88,166,255,0.10)",
      display: "flex",
      flexDirection: "column",
      padding: "0 16px 4px",
      userSelect: "none",
      height: 104,
    }}>

      <div role="status" className="history-status" data-state={recoveryStatus==="error"||recoveryStatus==="limited"?recoveryStatus:historyTruncated?"limited":historyStatus}>
        {recoveryStatus==="loading"?"Recovering reports after connection · ":recoveryStatus==="error"?"Connection recovery incomplete · reports may be missing · ":recoveryStatus==="limited"?"Connection recovery limit reached · reports may be missing · ":""}
        {historyStatus==="loading"?"Loading report history…":historyStatus==="error"?"History unavailable · showing previously loaded reports":historyTruncated?`Display limit reached · newest ${MAX_LOADED_REPORTS.toLocaleString()} loaded reports · older history is incomplete`:`${allEvents.length.toLocaleString()} reports loaded · timeline reflects loaded coverage`}
      </div>
      {/* ── TOP ROW ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 0, height: 40, flexShrink: 0 }}>

        {/* Preset buttons */}
        <div style={{ display: "flex", alignItems: "center", gap: 3, marginRight: 14, flexShrink: 0 }}>
          {PRESETS.map((p) => {
            const isActive = activePreset === p.label;
            const accentColor = p.live ? "#3fb950" : "#d29922";
            return (
              <button
                key={p.label}
                onClick={() => {
                  setIsPlaying(false);
                  onReplayCursorChange?.(null);
                  setActivePreset(p.label);
                  onRangeChange(makeRangeForPreset(p,conflictStart));
                  if (p.ms === "all" && onLoadHistory) onLoadHistory();
                }}
                title={p.ms === "all"
                  ? `Request loaded history from ${formatTimeLabel(conflictStart)}; display capped at ${MAX_LOADED_REPORTS} reports`
                  : `Last ${p.label}${p.live ? " · auto-follows live" : ""}`}
                style={{
                  padding: "4px 11px",
                  fontFamily: "var(--font-mono, monospace)",
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 0.8,
                  borderRadius: 3,
                  cursor: "pointer",
                  border: isActive
                    ? `1px solid ${accentColor}bb`
                    : "1px solid rgba(88,166,255,0.13)",
                  background: isActive
                    ? `${accentColor}18`
                    : "rgba(6,10,15,0.6)",
                  color: isActive ? accentColor : "#8b9eaf",
                  transition: "color 0.15s, background 0.15s, border-color 0.15s",
                  position: "relative",
                }}
              >
                {p.label}
                {/* Pulsing dot for live presets when active */}
                {isActive && p.live && (
                  <span style={{
                    position: "absolute", top: 3, right: 3,
                    width: 3, height: 3, borderRadius: "50%",
                    background: "#3fb950",
                    boxShadow: "0 0 4px rgba(63,185,80,0.9)",
                    animation: "pulse 1.5s ease-in-out infinite",
                  }} />
                )}
              </button>
            );
          })}
        </div>

        {/* Divider */}
        <div style={{ width: 1, height: 20, background: "rgba(88,166,255,0.08)", marginRight: 10, flexShrink: 0 }} />

        {/* Replay controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 3, marginRight: 14, flexShrink: 0 }}>
          <button
            onClick={handlePlayPause}
            title={isPlaying ? "Pause replay" : replayCursor!=null ? "Resume replay" : "Replay events in current window"}
            style={{
              padding: "4px 10px",
              fontFamily: "var(--font-mono, monospace)",
              fontSize: 12,
              fontWeight: 700,
              borderRadius: 3,
              cursor: "pointer",
              border: isPlaying ? "1px solid rgba(248,81,73,0.6)" : "1px solid rgba(88,166,255,0.13)",
              background: isPlaying ? "rgba(248,81,73,0.12)" : "rgba(6,10,15,0.6)",
              color: isPlaying ? "#f85149" : "#8b9eaf",
              transition: "all 0.15s",
              lineHeight: 1,
            }}
          >
            {isPlaying ? "Ⅱ" : "▶"}
          </button>
          <button
            onClick={handleSpeedChange}
            title="Change replay speed (click to cycle)"
            style={{
              padding: "4px 8px",
              fontFamily: "var(--font-mono, monospace)",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: 0.5,
              borderRadius: 3,
              cursor: "pointer",
              border: isPlaying ? "1px solid rgba(210,153,34,0.5)" : "1px solid rgba(88,166,255,0.13)",
              background: isPlaying ? "rgba(210,153,34,0.1)" : "rgba(6,10,15,0.6)",
              color: isPlaying ? "#d29922" : "#8b9eaf",
              transition: "all 0.15s",
            }}
          >
            {REPLAY_SPEED_LABELS[replaySpeed] ?? `${replaySpeed}x`}
          </button>
        </div>

        {/* Divider */}
        <div style={{ width: 1, height: 20, background: "rgba(88,166,255,0.08)", marginRight: 14, flexShrink: 0 }} />

        {/* Stats */}
        <div className="timeline-stats" style={{
          flex: 1, display: "flex", gap: 16, alignItems: "center",
          fontFamily: "var(--font-mono, monospace)", fontSize: 11, letterSpacing: 0.6,
          overflow: "hidden",
        }}>
          <span style={{ color: "#8b9eaf", whiteSpace: "nowrap" }}>
            DAY <span style={{ color: "#d29922", fontWeight: 700 }}>{currentDay}</span>
          </span>
          <span style={{ color: "#8b9eaf", whiteSpace: "nowrap" }}>
            <span style={{ color: "#58a6ff", fontWeight: 700 }}>{windowEvents.length}</span>
            <span style={{ color: "#8b9eaf" }}> / {geoEvents.length} MAPPED REPORTS</span>
          </span>
          {windowEvents.filter((e) => e.severity >= 7).length > 0 && (
            <span style={{ whiteSpace: "nowrap" }}>
              <span style={{ color: "#f85149", fontWeight: 700 }}>{windowEvents.filter((e) => e.severity >= 7).length}</span>
              <span style={{ color: "#a3b9ca" }}> HIGH</span>
            </span>
          )}
          <span style={{ color: "#a3b9ca", fontSize: 11, whiteSpace: "nowrap" }}>← → KEYS · DRAG</span>
        </div>

        {/* Time display */}
        <div className="timeline-time" style={{ flexShrink: 0, textAlign: "right", minWidth: 210, fontFamily: "var(--font-mono, monospace)" }}>
          {replayCursor != null ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8 }}>
              <span style={{
                fontSize: 11, padding: "2px 6px", borderRadius: 2,
                background: "rgba(248,81,73,0.12)", color: "#f85149",
                border: "1px solid rgba(248,81,73,0.4)", fontWeight: 700, letterSpacing: 1,
                animation: "pulse 1.5s ease-in-out infinite",
              }}>
                {isPlaying ? `▶ REPLAY ${REPLAY_SPEED_LABELS[replaySpeed]}` : "Ⅱ REPLAY PAUSED"}
              </span>
              <span style={{ fontSize: 11, color: "#f85149" }}>
                {formatTimeLabel(new Date(replayCursor))}
              </span>
            </div>
          ) : isLivePreset ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8 }}>
              <span style={{
                fontSize: 11, padding: "2px 6px", borderRadius: 2,
                background: "rgba(63,185,80,0.1)", color: "#3fb950",
                border: "1px solid rgba(63,185,80,0.3)", fontWeight: 700, letterSpacing: 1,
              }}>
                {SHOWCASE ? "● EXERCISE" : "● LIVE"}
              </span>
              <span style={{ fontSize: 11, color: "#a3b9ca" }}>
                {formatTimeLabel(new Date(winStart))} →
              </span>
            </div>
          ) : activePreset === "ALL" ? (
            <span style={{ fontSize: 11, color: "#a3b9ca", fontWeight: 700 }}>LOADED HISTORY</span>
          ) : (
            <div style={{ fontSize: 11, color: "#8b9eaf", lineHeight: 1.6 }}>
              <div>{formatTimeLabel(new Date(winStart))}</div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 6 }}>
                <span>{formatTimeLabel(new Date(winEnd))}</span>
                <span style={{ color: "#a3b9ca" }}>({formatDuration(windowSpan)})</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── TIMELINE TRACK ── */}
      <div style={{ flex: 1, position: "relative", paddingBottom: 4 }}>

        {/* Density histogram */}
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 14, top: 0, overflow: "hidden" }}>
          {densityBuckets.map((b) => (
            <div key={b.ts} style={{
              position: "absolute",
              left: `${b.pct}%`,
              width: `${Math.max(b.widthPct, 0.3)}%`,
              bottom: 0,
              height: `${Math.max(b.heightFrac * 100, b.total > 0 ? 8 : 0)}%`,
              background: b.military > b.total / 2
                ? `rgba(248,81,73,${0.07 + b.heightFrac * 0.22})`
                : `rgba(88,166,255,${0.05 + b.heightFrac * 0.15})`,
              borderTop: b.total > 0
                ? `1px solid ${b.military > b.total / 2 ? "rgba(248,81,73,0.3)" : "rgba(88,166,255,0.2)"}`
                : "none",
              borderRadius: "1px 1px 0 0",
            }} title={b.total > 0 ? `${formatDayLabel(new Date(b.ts))}: ${b.total} events` : undefined} />
          ))}
        </div>

        {/* Track */}
        <div
          ref={trackRef}
          onClick={onTrackClick}
          style={{
            position: "absolute", left: 0, right: 0, bottom: 14, height: 6,
            background: "rgba(20,30,45,0.9)", borderRadius: 3, cursor: "crosshair",
          }}
        >
          {/* Event ticks */}
          {ticks.map((tick, i) => (
            <div key={i} style={{
              position: "absolute", left: `${tick.pct}%`, top: "50%",
              transform: "translate(-50%, -50%)",
              width: tick.severity >= 7 ? 2 : 1,
              height: 4 + tick.severity * 1.2,
              background: EVENT_COLORS[tick.type] || "#666",
              opacity: 0.7, borderRadius: 1, pointerEvents: "none",
            }} />
          ))}

          {/* Dim outside selection */}
          <div style={{
            position: "absolute", left: 0, width: `${Math.max(0, leftPct)}%`,
            top: 0, bottom: 0, background: "rgba(0,0,0,0.55)", pointerEvents: "none",
            borderRadius: "3px 0 0 3px",
          }} />
          <div style={{
            position: "absolute", left: `${Math.min(100, leftPct + widthPct)}%`, right: 0,
            top: 0, bottom: 0, background: "rgba(0,0,0,0.55)", pointerEvents: "none",
            borderRadius: "0 3px 3px 0",
          }} />

          {/* Draggable window */}
          <div
            onMouseDown={(e) => onMouseDown(e, "window")}
            style={{
              position: "absolute", left: `${leftPct}%`, width: `${widthPct}%`,
              top: -1, bottom: -1,
              background: "rgba(88,166,255,0.04)",
              border: `1px solid ${isLivePreset ? "rgba(63,185,80,0.4)" : "rgba(88,166,255,0.28)"}`,
              borderRadius: 2, cursor: "grab",
            }}
          />
          {/* Handles */}
          {[["left", leftPct], ["right", leftPct + widthPct]].map(([side, pct]) => (
            <div
              key={side as string}
              onMouseDown={(e) => onMouseDown(e, side as "left" | "right")}
              style={{
                position: "absolute",
                left: `${pct}%`, top: -3, bottom: -3, width: 5,
                transform: "translateX(-50%)", cursor: "ew-resize",
                background: isLivePreset ? "#3fb950" : "#58a6ff",
                borderRadius: 2, opacity: 0.85,
              }}
            />
          ))}

          {/* Replay cursor */}
          {replayCursor != null && replayCursor >= winStart && replayCursor <= winEnd && (
            <div style={{
              position: "absolute",
              left: `${((replayCursor - rangeStart) / fullSpan) * 100}%`,
              top: -4, bottom: -4, width: 2,
              background: "#f85149", borderRadius: 1,
              boxShadow: "0 0 8px rgba(248,81,73,0.7)",
              transition: "left 0.05s linear",
              pointerEvents: "none",
            }} />
          )}

          {/* "Now" edge pulse */}
          <div style={{
            position: "absolute", right: 0, top: -2, bottom: -2, width: 2,
            background: "#3fb950", borderRadius: 1,
            boxShadow: "0 0 6px rgba(63,185,80,0.5)",
          }} />
        </div>

        {/* Day labels */}
        <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 13 }}>
          {dayLabels.map((d) => (
            <div key={d.ts} data-axis-day={d.dayNum} title={formatTimeLabel(new Date(d.ts))} style={{
              position: "absolute",
              left: `${d.pct}%`,
              transform: d.pct<1?"none":d.pct>98?"translateX(-100%)":"translateX(-50%)",
              fontFamily: "var(--font-mono, monospace)",
              fontSize: 11,
              color: "#8b9eaf",
              letterSpacing: 0.3,
              whiteSpace: "nowrap",
              pointerEvents: "none",
            }}>
              D{d.dayNum}
            </div>
          ))}
          <div style={{
            position: "absolute", left: "0%", top: -34, bottom: 0, width: 1,
            background: "rgba(248,81,73,0.4)", boxShadow: "0 0 4px rgba(248,81,73,0.25)",
            pointerEvents: "none",
          }} title={`${formatTimeLabel(conflictStart)} — configured history start`} />
        </div>
      </div>
    </div>
  );
}
