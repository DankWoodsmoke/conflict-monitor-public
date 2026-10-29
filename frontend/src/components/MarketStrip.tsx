import { apiFetch } from "../lib/api";
import { API_BASE } from "../lib/runtime";
/**
 * MarketStrip — live economic indicators with sparkline history
 * Shows Brent, WTI, Gold, VIX, USD/ILS, S&P 500 with mini SVG sparklines
 */
import { useEffect, useRef, useState } from "react";


const POLL_MS  = 5 * 60 * 1000;
const HISTORY_MAX = 20;

interface Ticker {
  symbol:       string;
  name:         string;
  unit:         string;
  category:     string;
  price:        number;
  change_pct:   number | null;
  change_abs:   number | null;
  market_state: string;
}
interface MarketResponse {
  data: Ticker[];
  stale: boolean;
  cached_ago: number;
  status?:string;
}

function fmtPrice(t: Ticker): string {
  const p = t.price;
  if (t.category === "equity") return p >= 1000 ? p.toLocaleString("en-US", { maximumFractionDigits: 0 }) : p.toFixed(2);
  if (t.category === "fear")   return p.toFixed(2);
  if (t.category === "fx")     return p.toFixed(4);
  return p.toFixed(2);
}
function fmtChange(pct: number | null): string {
  if (pct === null) return "";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}
function changeColor(t: Ticker): string {
  if (t.change_pct === null) return "var(--text-secondary)";
  const up = t.change_pct >= 0;
  if (t.category === "fear") return up ? "#f85149" : "#3fb950";
  return up ? "#3fb950" : "#f85149";
}
function arrow(pct: number | null): string {
  if (pct === null) return "";
  return pct >= 0 ? "▲" : "▼";
}

// ── Mini SVG sparkline ────────────────────────────────────────────────────
function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return <svg width={44} height={18} />;
  const W = 44, H = 18;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * (W - 2) + 1;
    const y = H - 1 - ((v - min) / range) * (H - 4) - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const ptsArr = pts.split(" "); const lastY = parseFloat(ptsArr[ptsArr.length - 1].split(",")[1]);

  return (
    <svg width={W} height={H} style={{ flexShrink: 0, overflow: "visible" }}>
      {/* Area fill under sparkline */}
      <defs>
        <linearGradient id={`sg-${color.replace("#","")}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={`1,${H} ${pts} ${W - 1},${H}`}
        fill={`url(#sg-${color.replace("#","")})`}
      />
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.85"
      />
      {/* Last price dot */}
      <circle
        cx={(data.length - 1) / (data.length - 1) * (W - 2) + 1}
        cy={lastY}
        r="1.8"
        fill={color}
        opacity="0.9"
      />
    </svg>
  );
}

export function MarketStrip() {
  const [tickers, setTickers]   = useState<Ticker[]>([]);
  const [stale,   setStale]     = useState(false);
  const [status,setStatus]=useState<"loading"|"ready"|"disabled"|"unavailable"|"stale">("loading");
  const [history, setHistory]   = useState<Map<string, number[]>>(new Map());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = async () => {
    try {
      const r = await apiFetch(`${API_BASE}/market`);
      if (!r.ok) throw new Error("Market snapshot unavailable");
      const json: MarketResponse = await r.json();
      if(!Array.isArray(json.data))throw new Error("Invalid market snapshot");
      json.data=json.data.filter(t=>t&&typeof t.symbol==="string"&&typeof t.price==="number"&&Number.isFinite(t.price));
      setTickers(json.data);setStale(json.stale || json.data.length===0);
      setStatus(json.data.length?(json.stale?"stale":"ready"):json.status==="disabled"?"disabled":json.status==="loading"?"loading":"unavailable");
      if (json.data.length > 0) {
        setTickers(json.data);
        setStale(json.stale);
        // Accumulate price history per symbol
        setHistory(prev => {
          const next = new Map(prev);
          json.data.forEach(t => {
            const arr = next.get(t.symbol) ?? [];
            next.set(t.symbol, [...arr.slice(-(HISTORY_MAX - 1)), t.price]);
          });
          return next;
        });
      }
    } catch {
      setStale(true);setStatus("unavailable");
    }
  };

  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(fetchData, POLL_MS);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  return (
    <div
      style={{
        gridArea: "market",
        display: "flex",
        alignItems: "center",
        padding: "0 14px",
        background: "rgba(6,10,15,0.98)",
        borderBottom: "1px solid var(--border)",
        gap: 0,
        overflow: "hidden",
        position: "relative",
        height: 30,
      }}
    >
      {/* Label */}
      <span style={{
        fontFamily: "var(--font-mono)",
        fontSize: 11,
        letterSpacing: 2,
        color: "#9fbdd0",
        marginRight: 12,
        flexShrink: 0,
        textTransform: "uppercase",
        fontWeight: 700,
      }}>
        MARKETS
      </span>

      {/* Tickers */}
      <div style={{ display: "flex", alignItems: "center", gap: 0, flex: 1, overflow: "hidden" }}>
        {tickers.length === 0 && (
          <span role="status" aria-label="Market data status" style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-secondary)", letterSpacing: 1 }}>
{status==="loading"?"Loading provider snapshot…":status==="disabled"?"Market provider disabled":"Market data unavailable"}
          </span>
        )}
        {tickers.map((t, i) => {
          const col     = changeColor(t);
          const closed  = t.market_state === "CLOSED";
          const hist    = history.get(t.symbol) ?? [];
          const sparkColor = t.change_pct === null ? "#58a6ff"
            : t.change_pct > 0
              ? (t.category === "fear" ? "#f85149" : "#3fb950")
              : (t.category === "fear" ? "#3fb950" : "#f85149");

          return (
            <div
              key={t.symbol}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                padding: "0 12px",
                borderRight: i < tickers.length - 1
                  ? "1px solid rgba(23,32,48,0.9)"
                  : "none",
                flexShrink: 0,
                height: "100%",
              }}
            >
              {/* Name */}
              <span style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                color: "#a3b9ca",
                letterSpacing: 0.8,
                fontWeight: 600,
              }}>
                {t.name}
              </span>

              {/* Sparkline */}
              {hist.length >= 2 && (
                <Sparkline data={hist} color={sparkColor} />
              )}

              {/* Price */}
              <span style={{
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                color: closed ? "var(--text-secondary)" : "var(--text-primary)",
                fontWeight: 700,
                letterSpacing: 0.3,
              }}>
                {t.unit === "$/bbl" || t.unit === "$/oz" ? "$" : ""}{fmtPrice(t)}
              </span>

              {/* Change */}
              {t.change_pct !== null && (
                <span style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  color: col,
                  fontWeight: 600,
                  opacity: 1,
                }}>
                  {arrow(t.change_pct)}{fmtChange(t.change_pct)}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {stale && tickers.length > 0 && (
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          color: "var(--accent-yellow)",
          letterSpacing: 1,
          flexShrink: 0,
          marginLeft: 8,
        }}>⚠ DELAYED</span>
      )}
    </div>
  );
}
