import { apiFetch } from "../lib/api";
import { API_BASE } from "../lib/runtime";
/**
 * Provider snapshots with retrieval context; quote clocks may be unavailable.
 * Shows Brent, WTI, Gold, VIX, USD/ILS, S&P 500 with mini SVG sparklines
 */
import { useEffect, useState } from "react";


const POLL_MS  = 5 * 60 * 1000;
const STARTUP_POLL_MS = [5000,10000,20000,30000];
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
  source: string;
  observation_time: string | null;
}
interface MarketResponse {
  data: Ticker[];
  stale: boolean;
  cached_ago: number;
  status?:string;
}

export function validateMarketSnapshot(value:unknown):MarketResponse {
  if(!value||typeof value!=="object"||Array.isArray(value))throw Error("Invalid market snapshot");
  const raw=value as MarketResponse;
  if(!Array.isArray(raw.data)||raw.data.length>30||typeof raw.stale!=="boolean"||raw.status!==undefined&&(typeof raw.status!=="string"||raw.status.length>40))throw Error("Invalid market snapshot");
  const age=raw.cached_ago===undefined&&!raw.data.length?-1:raw.cached_ago;
  if(typeof age!=="number"||!Number.isFinite(age)||age < -1)throw Error("Invalid retrieval age");
  const seen=new Set<string>();
  const text=(v:unknown,max:number,empty=false)=>typeof v==="string"&&v.length<=max&&(empty||v.length>0);
  const finite=(v:unknown)=>typeof v==="number"&&Number.isFinite(v);
  const data=raw.data.map(t=>{
    if(!t||typeof t!=="object"||!text(t.symbol,24)||seen.has(t.symbol)||!text(t.name,64)||!text(t.unit,20,true)||!text(t.category,40)||!text(t.market_state,40)||!finite(t.price)||
      t.change_pct!==null&&!finite(t.change_pct)||t.change_abs!==null&&!finite(t.change_abs)||
      t.source!==undefined&&!text(t.source,200)||t.observation_time!==undefined&&t.observation_time!==null&&(!text(t.observation_time,50)||!/^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/.test(t.observation_time)||!Number.isFinite(Date.parse(t.observation_time))||Date.parse(t.observation_time)>Date.now()+60000))throw Error("Invalid market observation");
    seen.add(t.symbol);
    return {...t,source:t.source||"Source unreported",observation_time:t.observation_time??null};
  });
  return {...raw,data,cached_ago:age};
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
  const [retrieval,setRetrieval]=useState<{at:string;age:number}|null>(null);

  useEffect(() => {
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined,expiry:ReturnType<typeof setTimeout>|undefined;
    let startup=true,startupPolls=0;
    const fetchData=async()=>{
      let nextPoll=POLL_MS;
      try{
        const response=await apiFetch(`${API_BASE}/market`,{signal:controller.signal});
        if(!response.ok)throw Error("Market snapshot unavailable");
        const json=validateMarketSnapshot(await response.json());
        if(controller.signal.aborted)return;
        // An empty successful loading response means the shared provider task is
        // still running. Check its cache briefly, then return to normal cadence.
        if(startup&&!json.data.length&&json.status==="loading"&&startupPolls<STARTUP_POLL_MS.length)nextPoll=STARTUP_POLL_MS[startupPolls++];
        else startup=false;
        const delayed=json.stale||json.cached_ago<0||json.cached_ago>=POLL_MS/1000;
        setTickers(json.data);setStale(delayed||!json.data.length);setRetrieval({at:new Date().toISOString(),age:json.cached_ago});
        setStatus(json.data.length?(delayed?"stale":"ready"):json.status==="disabled"?"disabled":json.status==="loading"?"loading":"unavailable");
        clearTimeout(expiry);
        if(json.data.length&&!delayed)expiry=setTimeout(()=>{if(!controller.signal.aborted){setStale(true);setStatus("stale");}},Math.max(0,POLL_MS-json.cached_ago*1000));
        if(json.data.length)setHistory(prev=>{
          const next=new Map<string,number[]>();
          for(const ticker of json.data){const values=prev.get(ticker.symbol)??[];next.set(ticker.symbol,[...values.slice(-(HISTORY_MAX-1)),ticker.price]);}
          return next;
        });
      }catch{startup=false;if(!controller.signal.aborted){setStale(true);setStatus("unavailable");}}
      finally{if(!controller.signal.aborted)timer=setTimeout(()=>void fetchData(),nextPoll);}
    };
    void fetchData();
    return()=>{controller.abort();clearTimeout(timer);clearTimeout(expiry);};
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
              tabIndex={0}
              aria-label={`${t.name} provider snapshot. Source: ${t.source}. Quote observation time: ${t.observation_time||"unknown"}. Market state: ${t.market_state}. ${stale?"Delayed or unavailable refresh. ":""}Retrieved ${retrieval?.at||"unknown"}; provider cache age at retrieval ${retrieval&&retrieval.age>=0?`${retrieval.age} seconds`:"unknown"}. Sparkline shows this session's sampled snapshots, not verified exchange history.`}
              title={`Source: ${t.source}\nQuote observation time: ${t.observation_time||"unknown; retrieval does not establish quote freshness"}\nMarket state: ${t.market_state}\nRetrieved: ${retrieval?.at||"unknown"}; cache age at retrieval: ${retrieval&&retrieval.age>=0?`${retrieval.age}s`:"unknown"}\n${stale?"Delayed or unavailable refresh. ":""}Sparkline: this session's sampled snapshots.`}
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

      {tickers.length>0&&<span title="Provider snapshot; retrieval time is separate from quote observation time." style={{fontFamily:"var(--font-mono)",fontSize:10,color:"#9fbdd0",flexShrink:0,marginLeft:8}}>{tickers.some(t=>!t.observation_time)?"SNAPSHOT · QUOTE TIME UNKNOWN":"SNAPSHOT"}</span>}

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
