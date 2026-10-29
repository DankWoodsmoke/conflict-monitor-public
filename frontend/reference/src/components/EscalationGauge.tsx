import { nowMs } from "../lib/clock";
import { apiFetch } from "../lib/api";
import { API_BASE } from "../lib/runtime";
/**
 * EscalationGauge — threat level arc + event frequency histogram + source breakdown
 */
import { useMemo, useEffect, useState } from "react";
import type { ConflictEvent } from "../types/event";



const WINDOW = 20;

function lerp(a: string, b: string, t: number): string {
  const parse = (hex: string) => {
    const h = hex.replace("#", "");
    return [parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16)];
  };
  const [r1,g1,b1] = parse(a);
  const [r2,g2,b2] = parse(b);
  return `rgb(${Math.round(r1+(r2-r1)*t)},${Math.round(g1+(g2-g1)*t)},${Math.round(b1+(b2-b1)*t)})`;
}

function gaugeColor(level: number): string {
  if (level <= 3) return lerp("#3fb950","#d29922",level/3);
  if (level <= 6) return lerp("#d29922","#f85149",(level-3)/3);
  return lerp("#f85149","#ff2020",(level-6)/4);
}

function statusLabel(level: number): { text: string; color: string } {
  if (level <= 2) return { text: "MONITORING",  color: "#3fb950" };
  if (level <= 4) return { text: "ELEVATED",    color: "#d29922" };
  if (level <= 6) return { text: "HIGH",        color: "#f0883e" };
  if (level <= 8) return { text: "HIGH ALERT",  color: "#f85149" };
  return               { text: "CRITICAL",      color: "#ff2020" };
}

// Source network classification
const NETWORK_MAP: Record<string, string> = {
  telegram: "TG", rss_x_: "X",
};
function classifyNetwork(src: string): string {
  if (!src) return "RSS";
  if (src === "telegram") return "TG";
  if (src.startsWith("x_")) return "X";
  if (src.startsWith("rss_x_")) return "X";
  if (["ukmto","us5thfleet","cmf_bahrain","tankertracker","safety4sea",
       "x_safety4sea","x_ukmto","x_us5thfleet","x_cmfbahrain","x_tankertracker"].some(s => src.includes(s))) return "MAR";
  return "RSS";
}

const NET_COLORS: Record<string, string> = {
  TG:  "#4dabf7",
  X:   "#74c0fc",
  RSS: "#69db7c",
  MAR: "#22d3ee",
};

interface Props { events: ConflictEvent[]; }

export function EscalationGauge({ events }: Props) {
  const [trend, setTrend] = useState<"up" | "down" | "stable">("stable");

  useEffect(() => {
    apiFetch(`${API_BASE}/events?limit=200`)
      .then(r => r.json())
      .then((data: any[]) => {
        const now = nowMs();
        const recent3h = data.filter((e: any) => now - new Date(e.timestamp).getTime() < 3 * 3600000).length;
        const prev3h = data.filter((e: any) => {
          const age = now - new Date(e.timestamp).getTime();
          return age >= 3 * 3600000 && age < 6 * 3600000;
        }).length;
        setTrend(recent3h > prev3h * 1.2 ? "up" : recent3h < prev3h * 0.8 ? "down" : "stable");
      })
      .catch(() => {});
  }, []);

  const level = useMemo(() => {
    const recent = events.slice(0, WINDOW);
    if (recent.length === 0) return 0;
    return Math.round(recent.reduce((s, e) => s + e.severity, 0) / recent.length * 10) / 10;
  }, [events]);

  // ── 12-hour event frequency histogram ──────────────────────────────────
  const hourBuckets = useMemo(() => {
    const now = nowMs();
    const buckets = Array(12).fill(0);
    events.forEach(e => {
      const ageH = (now - new Date(e.timestamp).getTime()) / 3600000;
      const slot = Math.floor(ageH);
      if (slot >= 0 && slot < 12) buckets[slot]++;
    });
    return buckets.reverse(); // oldest → newest
  }, [events]);

  const histMax = Math.max(...hourBuckets, 1);

  // ── Source network breakdown (last 6h) ────────────────────────────────
  const netBreakdown = useMemo(() => {
    const cutoff = nowMs() - 6 * 3600000;
    const counts: Record<string, number> = { TG: 0, X: 0, RSS: 0, MAR: 0 };
    events.filter(e => new Date(e.timestamp).getTime() > cutoff).forEach(e => {
      const n = classifyNetwork(e.source || e.channel_name || "");
      if (n in counts) counts[n]++;
    });
    const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
    return Object.entries(counts).map(([net, count]) => ({
      net, count, pct: count / total,
    })).filter(x => x.count > 0);
  }, [events]);

  const pct        = Math.min(level / 10, 1);
  const color      = gaugeColor(level);
  const status     = statusLabel(level);
  const glowIntensity = Math.min(level / 10, 1);
  const glowAlpha  = (0.08 + glowIntensity * 0.35).toFixed(2);
  const glowSpread = Math.round(4 + glowIntensity * 16);

  // SVG arc
  const radius = 58;
  const stroke = 10;
  const circumference = Math.PI * radius;
  const offset = circumference * (1 - pct);

  return (
    <div
      className="panel"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "12px 12px 10px",
        height: "100%",
        boxShadow: `0 0 ${glowSpread}px rgba(${level > 6 ? "248,81,73" : level > 3 ? "210,153,34" : "63,185,80"},${glowAlpha}), 0 0 1px var(--border-glow)`,
        transition: "box-shadow 1s ease",
        gap: 0,
      }}
    >
      {/* ── Arc gauge ─────────────────────────────────────────────────── */}
      <div style={{ position: "relative", width: 150, height: 82 }}>
        <svg width="150" height="82" viewBox="0 0 150 82">
          {/* Track glow */}
          <path
            d="M 8 76 A 58 58 0 0 1 142 76"
            fill="none" stroke={color} strokeWidth={stroke + 6}
            strokeLinecap="round" opacity="0.06"
          />
          {/* Background arc */}
          <path
            d="M 8 76 A 58 58 0 0 1 142 76"
            fill="none" stroke="rgba(23,32,48,0.9)" strokeWidth={stroke}
            strokeLinecap="round"
          />
          {/* Tick marks */}
          {[0,1,2,3,4,5,6,7,8,9,10].map(i => {
            const angle = -180 + (i / 10) * 180;
            const rad = (angle * Math.PI) / 180;
            const cx = 75 + 58 * Math.cos(rad);
            const cy = 76 + 58 * Math.sin(rad);
            const cx2 = 75 + 50 * Math.cos(rad);
            const cy2 = 76 + 50 * Math.sin(rad);
            return (
              <line key={i} x1={cx} y1={cy} x2={cx2} y2={cy2}
                stroke={i % 5 === 0 ? "rgba(88,166,255,0.25)" : "rgba(88,166,255,0.08)"}
                strokeWidth={i % 5 === 0 ? 1.5 : 0.75} />
            );
          })}
          {/* Foreground arc */}
          <path
            d="M 8 76 A 58 58 0 0 1 142 76"
            fill="none" stroke={color} strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{
              transition: "stroke-dashoffset 0.9s cubic-bezier(0.4,0,0.2,1), stroke 0.9s ease",
              filter: `drop-shadow(0 0 ${3 + glowIntensity * 8}px ${color})`,
            }}
          />
          {/* Level number */}
          <text x="75" y="62" textAnchor="middle"
            fill={color} fontSize="26" fontWeight="800"
            fontFamily="var(--font-mono)"
            style={{ transition: "fill 0.8s ease" }}
          >
            {level.toFixed(1)}
          </text>
          {/* /10 label */}
          <text x="75" y="74" textAnchor="middle"
            fill="rgba(77,96,122,0.7)" fontSize="8"
            fontFamily="var(--font-mono)"
          >/10</text>
        </svg>
      </div>

      {/* Status */}
      <div style={{
        fontSize: 12, fontWeight: 800, letterSpacing: 3,
        color: status.color, fontFamily: "var(--font-mono)",
        marginTop: 2,
        animation: level >= 7 ? "pulse 1.8s ease-in-out infinite" : undefined,
        textShadow: level >= 7 ? `0 0 10px ${status.color}88` : "none",
        display: "flex", alignItems: "center", gap: 4, justifyContent: "center",
      }}>
        <span>{status.text}</span>
        <span style={{
          color: trend === "up" ? "#f85149" : trend === "down" ? "#3fb950" : "#d29922",
          fontSize: 14, marginLeft: 2
        }}>
          {trend === "up" ? "↑" : trend === "down" ? "↓" : "→"}
        </span>
      </div>

      <div style={{
        fontSize: 11, letterSpacing: 1.5, color: "var(--text-secondary)",
        fontFamily: "var(--font-mono)", marginTop: 2, opacity: 0.5,
      }}>
        THREAT LEVEL · LAST {WINDOW}
      </div>

      {/* ── Divider ─────────────────────────────────────────────────────── */}
      <div style={{ width: "100%", height: 1, background: "var(--border)", margin: "8px 0 6px", opacity: 0.6 }} />

      {/* ── 12H Event Frequency Histogram ──────────────────────────────── */}
      <div style={{ width: "100%", paddingLeft: 4, paddingRight: 4 }}>
        <div style={{
          fontSize: 11, letterSpacing: 1.5, color: "rgba(88,166,255,0.35)",
          fontFamily: "var(--font-mono)", fontWeight: 700, marginBottom: 5,
        }}>
          ACTIVITY / 12H
        </div>
        <div style={{
          display: "flex", alignItems: "flex-end",
          gap: 2, height: 32, width: "100%",
        }}>
          {hourBuckets.map((count, i) => {
            const h = Math.max((count / histMax) * 28, count > 0 ? 2 : 1);
            const isRecent = i >= 10;
            const barColor = count > 15 ? "#f85149"
              : count > 8  ? "#f0883e"
              : count > 3  ? "#d29922"
              : "#3fb950";
            return (
              <div key={i} title={`${count} events`} style={{
                flex: 1, height: h,
                background: isRecent ? barColor : barColor + "88",
                borderRadius: "1px 1px 0 0",
                transition: "height 0.6s cubic-bezier(0.4,0,0.2,1)",
                cursor: "default",
                boxShadow: isRecent && count > 8 ? `0 0 4px ${barColor}66` : "none",
              }} />
            );
          })}
        </div>
        {/* X-axis: -11h … NOW */}
        <div style={{
          display: "flex", justifyContent: "space-between",
          marginTop: 3, paddingLeft: 1, paddingRight: 1,
        }}>
          <span style={{ fontSize: 11, color: "rgba(77,96,122,0.5)", fontFamily: "var(--font-mono)" }}>-11h</span>
          <span style={{ fontSize: 11, color: "rgba(88,166,255,0.6)", fontFamily: "var(--font-mono)", fontWeight: 700 }}>NOW</span>
        </div>
      </div>

      {/* ── Source breakdown (last 6h) ──────────────────────────────────── */}
      {netBreakdown.length > 0 && (
        <>
          <div style={{ width: "100%", height: 1, background: "var(--border)", margin: "7px 0 6px", opacity: 0.5 }} />
          <div style={{ width: "100%", paddingLeft: 4, paddingRight: 4 }}>
            <div style={{
              fontSize: 11, letterSpacing: 1.5, color: "rgba(88,166,255,0.35)",
              fontFamily: "var(--font-mono)", fontWeight: 700, marginBottom: 5,
            }}>
              SOURCES / 6H
            </div>
            {/* Stacked bar */}
            <div style={{
              display: "flex", height: 5, borderRadius: 3, overflow: "hidden", gap: 1,
            }}>
              {netBreakdown.map(({ net, pct: p }) => (
                <div key={net} title={`${net}: ${Math.round(p * 100)}%`}
                  style={{
                    flex: p, background: NET_COLORS[net] || "#58a6ff",
                    transition: "flex 0.5s ease",
                    boxShadow: `0 0 4px ${NET_COLORS[net] || "#58a6ff"}66`,
                  }}
                />
              ))}
            </div>
            {/* Legend */}
            <div style={{
              display: "flex", gap: 8, marginTop: 5, flexWrap: "wrap",
            }}>
              {netBreakdown.map(({ net, count, pct: p }) => (
                <div key={net} style={{ display: "flex", alignItems: "center", gap: 3 }}>
                  <div style={{
                    width: 5, height: 5, borderRadius: "50%",
                    background: NET_COLORS[net] || "#58a6ff",
                    flexShrink: 0,
                  }} />
                  <span style={{
                    fontSize: 11, color: NET_COLORS[net] || "#58a6ff",
                    fontFamily: "var(--font-mono)", fontWeight: 700,
                    opacity: 0.85,
                  }}>{net}</span>
                  <span style={{
                    fontSize: 11, color: "var(--text-secondary)",
                    fontFamily: "var(--font-mono)",
                  }}>{count}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
