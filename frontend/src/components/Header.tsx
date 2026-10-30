import { nowMs } from "../lib/clock";
import { SHOWCASE } from "../lib/runtime";
import { apiFetch } from "../lib/api";
import { API_BASE } from "../lib/runtime";
import { type CSSProperties, useEffect, useRef, useState, useCallback } from "react";
import type { ViewMode } from "../App";



// ── Live cost chip ────────────────────────────────────────────────────────────
function useCostData() {
  const [data, setData] = useState<any>(null);
  const fetch_ = useCallback(() => {
    apiFetch(`${API_BASE}/costs/summary`)
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => {});
  }, []);
  useEffect(() => {
    fetch_();
    const t = setInterval(fetch_, 10 * 60 * 1000); // refresh every 10 min
    return () => clearInterval(t);
  }, [fetch_]);
  return data;
}

export function CostChip({ mono }: { mono: string }) {
  const data = useCostData();
  const [open, setOpen] = useState(false);
  // Track button position for fixed-position dropdown (escapes all stacking contexts)
  const [dropPos, setDropPos] = useState({ top: 0, right: 0 });
  const btnRef = useRef<HTMLButtonElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        btnRef.current && !btnRef.current.contains(e.target as Node) &&
        dropRef.current && !dropRef.current.contains(e.target as Node)
      ) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleOpen = () => {
    if (btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      setDropPos({
        top: r.bottom + 6,
        right: window.innerWidth - r.right,
      });
    }
    setOpen(o => !o);
  };

  if (!data) return null;

  const avg    = data.avg_per_day_usd ?? null;
  if (avg == null) return <span style={{fontSize:11,color:"var(--text-secondary)"}}>COSTS UNAVAILABLE</span>;
  const fixed  = data.breakdown?.fixed_monthly ?? {};
  const claude = data.breakdown?.claude_api_tracked ?? {};
  const fm     = data.breakdown?.first_month ?? {};
  const ops: any[] = claude.operations ?? [];

  return (
    <div className="mobile-hide" style={{ position: "relative" }}>
      <button
        ref={btnRef}
        onClick={handleOpen}
        title="Site running cost since launch — click for breakdown"
        style={{
          background: "none",
          border: "1px solid #1a2a3a",
          borderRadius: 4,
          padding: "3px 8px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 5,
          fontFamily: mono,
          fontSize: 11,
          letterSpacing: 0.8,
          color: "#5a7a9a",
          transition: "all 0.15s",
          whiteSpace: "nowrap",
        }}
        onMouseEnter={e => {
          (e.currentTarget as HTMLElement).style.borderColor = "#829aae";
          (e.currentTarget as HTMLElement).style.color = "#7a9aba";
        }}
        onMouseLeave={e => {
          (e.currentTarget as HTMLElement).style.borderColor = "#1a2a3a";
          (e.currentTarget as HTMLElement).style.color = "#5a7a9a";
        }}
      >
        <span style={{ fontSize: 11, opacity: 0.7 }}>$</span>
        <span style={{ fontWeight: 700 }}>{avg.toFixed(2)}</span>
        <span style={{ fontSize: 11, opacity: 0.6 }}>/day</span>
      </button>

      {/* Fixed-position dropdown — renders above map/sidebar stacking contexts */}
      {open && (
        <div
          ref={dropRef}
          style={{
            position: "fixed",
            top: dropPos.top,
            right: dropPos.right,
            width: 288,
            background: "#07090f",
            border: "1px solid #1e2e3e",
            borderRadius: 6,
            padding: "12px 14px",
            zIndex: 9999,
            fontFamily: mono,
            boxShadow: "0 12px 48px rgba(0,0,0,0.85), 0 0 0 1px #0d1a2622",
          }}
        >
          {/* Title row */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: 2, color: "#8da3b7" }}>
              OPERATIONAL COSTS
            </span>
            <span style={{ fontSize: 11, color: "#2a3a4a" }}>Day {data.days_running}</span>
          </div>

          {/* Big avg */}
          <div style={{
            display: "flex", alignItems: "baseline", gap: 6,
            borderBottom: "1px solid #1a2a3a", paddingBottom: 10, marginBottom: 10,
          }}>
            <span style={{ fontSize: 24, fontWeight: 800, color: "#58a6ff", letterSpacing: -0.5, lineHeight: 1 }}>
              ${avg.toFixed(2)}
            </span>
            <span style={{ fontSize: 11, color: "#8da3b7" }}>avg / day since launch</span>
            <span style={{ marginLeft: "auto", fontSize: 11, color: "#829aae" }}>
              ${data.total_spend_usd?.toFixed(2)} total
            </span>
          </div>

          {/* How it's calculated note */}
          <div style={{
            fontSize: 11, color: "#2a3a4a", marginBottom: 10, lineHeight: 1.5,
            background: "rgba(88,166,255,0.03)", border: "1px solid #0d1a26",
            borderRadius: 3, padding: "5px 8px",
          }}>
            Average updates automatically after every SITREP generation and event
            classification call. Total ÷ days since launch.
          </div>

          {/* Total spend */}
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            fontSize: 11, color: "#8ea8be", marginBottom: 10,
          }}>
            <span>Total spent since Mar 9</span>
            <span style={{ color: "#6a9aba", fontWeight: 700 }}>${data.total_spend_usd?.toFixed(2)}</span>
          </div>

          {/* Build phase */}
          {fm.total > 0 && (
            <div style={{
              background: "rgba(88,166,255,0.05)", border: "1px solid #1a2a3a",
              borderRadius: 4, padding: "7px 9px", marginBottom: 8,
            }}>
              <div style={{ fontSize: 11, color: "#829aae", letterSpacing: 1.5, marginBottom: 4, fontWeight: 700 }}>
                BUILD PHASE (Mar 9 – Apr 1)
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#5a7a9a" }}>
                <span>All APIs, hosting, subscriptions</span>
                <span style={{ color: "#7a9aba", fontWeight: 700, flexShrink: 0, marginLeft: 8 }}>
                  ${(fm.total as number).toFixed(2)}
                </span>
              </div>
            </div>
          )}

          {/* Ongoing fixed */}
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 11, color: "#829aae", letterSpacing: 1.5, marginBottom: 5, fontWeight: 700 }}>
              ONGOING FIXED / MONTH
            </div>
            {[
              ["Server Hosting",  fixed.server_hosting],
              ["X / Grok API",    fixed.x_api],
              ["Speech API",      fixed.speech_api],
              ["Claude Pro",      fixed.claude_sub || null],
            ].filter(([, v]) => v).map(([label, val]) => (
              <div key={label as string} style={{
                display: "flex", justifyContent: "space-between",
                fontSize: 11, color: "#5a7a9a", marginBottom: 3,
              }}>
                <span>{label as string}</span>
                <span style={{ color: "#7a9aba" }}>${(val as number).toFixed(2)}/mo</span>
              </div>
            ))}
          </div>

          {/* Live Claude API tracking */}
          <div style={{ borderTop: "1px solid #0d1a26", paddingTop: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
              <div style={{
                width: 5, height: 5, borderRadius: "50%",
                background: ops.length > 0 ? "#3fb950" : "#8da3b7",
                flexShrink: 0,
                animation: ops.length > 0 ? "statusPulse 2s ease-in-out infinite" : "none",
              }} />
              <span style={{ fontSize: 11, color: ops.length > 0 ? "#3fb950" : "#829aae", letterSpacing: 1.5, fontWeight: 700 }}>
                CLAUDE API — LIVE TRACKING {ops.length > 0 ? "ACTIVE" : "PENDING"}
              </span>
            </div>
            {ops.length === 0 ? (
              <div style={{ fontSize: 11, color: "#2a3a4a", paddingLeft: 11 }}>
                Logs each SITREP + classification call. Will appear after next generation.
              </div>
            ) : (
              <>
                {ops.map(op => (
                  <div key={op.operation + op.model} style={{
                    display: "flex", justifyContent: "space-between", alignItems: "baseline",
                    fontSize: 11, color: "#5a7a9a", marginBottom: 3,
                  }}>
                    <span style={{ textTransform: "capitalize" }}>
                      {op.operation}
                      <span style={{ fontSize: 11, opacity: 0.5, marginLeft: 4 }}>
                        ×{op.calls} calls · {(op.input_tokens + op.output_tokens).toLocaleString()} tokens
                      </span>
                    </span>
                    <span style={{ color: "#3fb950", fontWeight: 700 }}>${op.cost_usd.toFixed(4)}</span>
                  </div>
                ))}
                <div style={{
                  fontSize: 11, color: "#829aae", marginTop: 5, paddingTop: 5,
                  borderTop: "1px solid #0d1a26",
                }}>
                  Every API call is logged in real time — average adjusts automatically
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface HeaderProps {
  isConnected: boolean;
  escalationLevel?: "STABLE" | "ELEVATED" | "ESCALATING" | "CRITICAL" | "UNASSESSED";
  eventCount: number;
  aircraftCount: number;
  vesselCount: number;

  demoMode: boolean;
  onAboutClick: () => void;
  onSettingsClick: () => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  activeSources: Set<string>;
  onSourceToggle: (src: string) => void;
  earthFocused?: boolean;
  onEarthFocusChange?: () => void;
}

function formatUTCTime(): string {
  const now = new Date(nowMs());
  const months = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
  ];
  const day = String(now.getUTCDate()).padStart(2, "0");
  const month = months[now.getUTCMonth()];
  const year = now.getUTCFullYear();
  const hours = String(now.getUTCHours()).padStart(2, "0");
  const minutes = String(now.getUTCMinutes()).padStart(2, "0");
  const seconds = String(now.getUTCSeconds()).padStart(2, "0");
  return `${day} ${month} ${year} | ${hours}:${minutes}:${seconds} UTC`;
}

const VIEW_OPTIONS: { mode: ViewMode; label: string; title: string }[] = [
  { mode: "earth", label: "Earth", title: "Earth — reports, tracking and Google imagery" },
  { mode: "media", label: "Media", title: "Media — broadcasts and cameras" },
  { mode: "sitrep", label: "Brief", title: "Situation brief — analysis and source evidence" },
];

// ── Source filter dropdown ─────────────────────────────────────────────────────
function SourceFilterDropdown({
  activeSources,
  onSourceToggle,
}: {
  activeSources: Set<string>;
  onSourceToggle: (src: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [dropPos, setDropPos] = useState<{ top: number; right: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (btnRef.current && !btnRef.current.closest("[data-src-dropdown]")?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const SOURCES: { id: "telegram" | "rss" | "x" | "sensor" | "other"; label: string; desc: string; color: string }[] = [
    { id: "telegram", label: "TG",  desc: "Telegram channels",   color: "#4dabf7" },
    { id: "rss",      label: "RSS", desc: "RSS news feeds",      color: "#f59e0b" },
    {id:"sensor",label:"SENSOR",desc:"Satellite thermal observations",color:"#c6a1f4"},
    {id:"other",label:"OTHER",desc:"Other or unidentified source family",color:"#a3b9ca"},
    { id: "x",        label: "X",   desc: "X / Twitter posts",   color: "#74c0fc" },
  ];

  // Count active sources for badge
  const activeCount = SOURCES.filter(s => activeSources.has(s.id)).length;
  const allOn = activeCount === SOURCES.length;

  return (
    <div data-src-dropdown style={{ position: "relative" }}>
      <button
        ref={btnRef}
        onClick={() => {
          if (!open && btnRef.current) {
            const rect = btnRef.current.getBoundingClientRect();
            setDropPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
          }
          setOpen(o => !o);
        }}
        title="Filter by source type"
        aria-expanded={open} aria-controls="source-family-picker"
        style={{
          background: open ? "rgba(88,166,255,0.12)" : "rgba(10,14,20,0.7)",
          border: `1px solid ${open ? "rgba(88,166,255,0.4)" : "rgba(88,166,255,0.15)"}`,
          borderRadius: 3, padding: "2px 8px",
          fontSize: 11, fontWeight: 700, letterSpacing: 1.2,
          fontFamily: "var(--font-mono)",
          color: open ? "#58a6ff" : "var(--text-secondary)",
          cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
          transition: "all 0.15s",
        }}
      >
        {!allOn && (
          <span style={{
            width: 5, height: 5, borderRadius: "50%",
            background: "#f59e0b", flexShrink: 0,
          }} />
        )}
        SOURCES
        <span style={{ fontSize: 11, opacity: 0.7 }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div id="source-family-picker" role="group" aria-label="Source categories" onKeyDown={event=>{if(event.key==="Escape"){event.preventDefault();event.stopPropagation();setOpen(false);btnRef.current?.focus();}}}
          style={{
            position: "fixed",
            top: dropPos ? dropPos.top : 0,
            right: dropPos ? dropPos.right : 0,
            zIndex: 9999,
            background: "rgba(6,10,15,0.97)",
            border: "1px solid rgba(88,166,255,0.25)",
            borderRadius: 4, padding: "6px 8px",
            minWidth: 148,
            boxShadow: "0 4px 20px rgba(0,0,0,0.6)",
          }}
        >
          <div style={{
            fontSize: 11, letterSpacing: 1.5, color: "#8b9eaf",
            fontFamily: "var(--font-mono)", fontWeight: 700,
            marginBottom: 6, textTransform: "uppercase",
          }}>
            Filter Sources
          </div>
          {SOURCES.map(({ id, label, desc, color }) => {
            const on = activeSources.has(id);
            return (
              <label
                key={id}
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "4px 2px", cursor: "pointer",
                  userSelect: "none", minHeight:30,
                  transition: "opacity 0.15s",
                }}
              >
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => onSourceToggle(id)}
                  style={{width:14,height:14,accentColor:color,margin:0}}
                />
                <span style={{
                  fontSize: 11, fontFamily: "var(--font-mono)",
                  color: on ? "#b0bec5" : "#96a8b8", letterSpacing: 0.5,
                }}>
                  <strong style={{ color: on ? color : "#96a8b8" }}>{label}</strong>
                  {" "}{desc}
                </span>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function Header({
  isConnected,
  escalationLevel = "UNASSESSED",
  eventCount,
  aircraftCount,
  vesselCount,
  demoMode,
  onAboutClick,
  onSettingsClick,
  viewMode,
  onViewModeChange,
  activeSources,
  onSourceToggle,
  earthFocused = false,
  onEarthFocusChange,
}: HeaderProps) {
  const [utcTime, setUtcTime] = useState(formatUTCTime);

  useEffect(() => {
    const interval = setInterval(() => setUtcTime(formatUTCTime()), 1000);
    return () => clearInterval(interval);
  }, []);

  const iconBtnStyle: CSSProperties = {
    background: "none",
    border: "1px solid var(--border)",
    color: "var(--text-secondary)",
    cursor: "pointer",
    borderRadius: 4,
    padding: "3px 8px",
    fontSize: 12,
    lineHeight: 1,
    display: "flex",
    alignItems: "center",
    gap: 4,
    transition: "all 0.15s ease",
    fontFamily: "var(--font-sans)",
  };

  const LEVEL_COLORS: Record<string, string> = {
    STABLE:     "#3fb950",
    ELEVATED:   "#d29922",
    ESCALATING: "#f0883e",
    CRITICAL:   "#f85149",
  };
  const levelColor = LEVEL_COLORS[escalationLevel] ?? "#91a9bb";
  const isAlert = escalationLevel === "ESCALATING" || escalationLevel === "CRITICAL";

  return (
    <header
      className="panel app-header"
      style={{
        gridArea: "header",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 20px",
        borderBottom: `1px solid ${levelColor}55`,
        boxShadow: `0 1px 0 ${levelColor}22, inset 0 -1px 0 ${levelColor}18`,
        background: `linear-gradient(180deg, rgba(6,10,15,0.99) 0%, rgba(10,14,23,0.98) 100%)`,
        position: "relative",
        zIndex: 50,
      }}
    >
    {/* Threat-level accent line at very bottom of header */}
    <div style={{
      position: "absolute", bottom: 0, left: 0, right: 0, height: 2,
      background: `linear-gradient(90deg, transparent 0%, ${levelColor}88 20%, ${levelColor} 50%, ${levelColor}88 80%, transparent 100%)`,
      animation: undefined,
      opacity: 0.8,
    }} />
      {/* Left: Title + Subtitle + Demo Badge */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
        <h1
          style={{
            fontSize: 15,
            fontWeight: 800,
            letterSpacing: 4,
            fontFamily: "var(--font-mono)",
            color: "var(--text-primary)",
            textShadow: isAlert ? `0 0 20px ${levelColor}66` : "none",
            transition: "text-shadow 1s ease",
          }}
        >
          <span style={{ color: levelColor, marginRight: 6, fontSize: 11 }}>⬡</span>
          CONFLICT MONITOR
        </h1>
        <span
          className="mobile-hide"
          style={{
            fontSize: 11,
            letterSpacing: 2,
            color: "var(--text-secondary)",
            fontWeight: 500,
          }}
        >
          REPORTS · CONTEXT · EVIDENCE
        </span>
        {demoMode && (
          <span
            className="header-demo-badge"
            style={{
              fontSize: 11,
              padding: "2px 6px",
              borderRadius: 2,
              background: "rgba(210, 153, 34, 0.2)",
              color: "var(--accent-yellow)",
              fontWeight: 700,
              letterSpacing: 1,
              fontFamily: "var(--font-mono)",
            }}
          >
            DEMO
          </span>
        )}
      </div>

      <nav className="view-tab-group" aria-label="Workspace views">
        {VIEW_OPTIONS.map(({ mode, label, title }) => <button key={mode} aria-label={title}
          aria-pressed={viewMode === mode} title={title} onClick={() => onViewModeChange(mode)}>{label}</button>)}
      </nav>

      {/* Center: UTC Clock */}
      <div
        className="mobile-hide"
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          fontWeight: 600,
          color: "#58a6ff",
          letterSpacing: 1.5,
          opacity: 0.85,
          animation: undefined,
        }}
      >
        {utcTime}
      </div>

      {/* Workspace tools */}
      <div className="header-tools" style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {/* Counts */}
        <div
          className="mobile-hide"
          style={{
            display: "flex",
            gap: 12,
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--text-secondary)",
            letterSpacing: 1,
          }}
        >
          <span>{eventCount} EVT</span>
          <span style={{ opacity: 0.4 }}>|</span>
          <span>{aircraftCount} AC</span>
          <span style={{ opacity: 0.4 }}>|</span>
          <span>{vesselCount} VES</span>
        </div>
        {/* Source filter — compact dropdown */}
        <SourceFilterDropdown activeSources={activeSources} onSourceToggle={onSourceToggle} />

        {/* Live status dot */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: isConnected
                ? (isAlert ? levelColor : "var(--accent-green)")
                : "var(--accent-red)",
              animation: undefined,
            }}
          />
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: 1,
              color: isConnected ? "var(--accent-green)" : "var(--accent-red)",
            }}
          >
            {SHOWCASE ? "EXERCISE" : isConnected ? "TRANSPORT UP" : "DISCONNECTED"}
          </span>
        </div>

        {/* Cost chip */}
        <div className="header-costs"><CostChip mono="var(--font-mono)" /></div>

        {/* Divider */}
        <div style={{ width: 1, height: 16, background: "var(--border)", opacity: 0.5 }} />

        {viewMode==="earth"&&onEarthFocusChange&&<button onClick={onEarthFocusChange} className="header-action earth-focus-control" aria-pressed={earthFocused} aria-label={earthFocused?"Restore reports and timeline":"Focus Earth — expand workspace"} title={earthFocused?"Restore reports, markets and timeline":"Give Earth the full workspace"}><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d={earthFocused?"M3 9h6V3m6 0v6h6M3 15h6v6m6 0v-6h6":"M9 3H3v6m12-6h6v6M3 15v6h6m6 0h6v-6"}/></svg><span>{earthFocused?"Restore":"Focus Earth"}</span></button>}
        <button onClick={onSettingsClick} className="header-action" title="Configure Earth and data providers">Settings</button>
        {/* About button */}
        <button
          onClick={onAboutClick}
          className="header-action"
          aria-label="Methods and evidence limitations"
          title="About this dashboard"
          style={iconBtnStyle}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--accent-blue)";
            (e.currentTarget as HTMLButtonElement).style.color = "var(--accent-blue)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
            (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)";
          }}
        >
          <span>Methods</span>
        </button>

      </div>


    </header>
  );
}
