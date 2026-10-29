import { nowMs } from "../lib/clock";
import { apiFetch } from "../lib/api";
/**
 * AircraftLayer.tsx — ADSBexchange-style aircraft overlay for Conflict Monitor
 *
 * Direct adsb.lol V2 API integration with:
 *  - Altitude color gradient (tar1090 palette)
 *  - Type-specific SVG silhouette icons
 *  - Detail panel, aircraft table, filter bar
 *  - Track trail history
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════

export interface ADSBAircraft {
  hex: string;
  flight?: string;
  r?: string;           // registration
  t?: string;           // ICAO type code
  desc?: string;        // type description (e.g. L2J)
  dbFlags?: number;     // bitfield: military=&1, interesting=&2, PIA=&4, LADD=&8
  lat?: number;
  lon?: number;
  alt_baro?: number | "ground";
  alt_geom?: number;
  gs?: number;          // ground speed knots
  track?: number;       // heading degrees
  baro_rate?: number;   // fpm
  squawk?: string;
  emergency?: string;
  category?: string;    // emitter category A0-D7
  seen?: number;        // seconds since last message
  seen_pos?: number;    // seconds since last position
  rssi?: number;
  type?: string;        // data source: adsb_icao, mlat, tisb, etc.
  nav_altitude_mcp?: number;
  nav_heading?: number;
  ias?: number;
  tas?: number;
  mach?: number;
  roll?: number;
  mag_heading?: number;
  true_heading?: number;
  wd?: number;          // wind direction
  ws?: number;          // wind speed
  oat?: number;         // outside air temp
  tat?: number;         // total air temp
  nic?: number;
  rc?: number;
  nac_p?: number;
  nac_v?: number;
  sil?: number;
  gva?: number;
  sda?: number;
  alert?: number;
  spi?: number;
}

interface ADSBResponse {
  ac: ADSBAircraft[];
  now: number;
  total: number;
  ctime?: number;
  ptime?: number;
}

export interface TrackPoint {
  lat: number;
  lon: number;
  alt: number | "ground";
  ts: number;
}

export interface AircraftFilters {
  callsign?: string;
  typeCode?: string;
  squawk?: string;
  altMin?: number;
  altMax?: number;
  militaryOnly?: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════════════════════════

// Proxy through Vite/nginx to avoid CORS — falls back to direct for non-browser contexts
const ADSB_API = "/adsb-api";
const STALE_TIMEOUT_S = 300; // 5 minutes — prune aircraft not seen in this window

// Emergency squawk codes
const EMERGENCY_SQUAWKS: Record<string, { label: string; color: string }> = {
  "7700": { label: "MAYDAY", color: "#ff4040" },
  "7600": { label: "RADIO FAIL", color: "#f59e0b" },
  "7500": { label: "HIJACK", color: "#ff4040" },
};

// ═══════════════════════════════════════════════════════════════════════════════
// Altitude Color Gradient — tar1090/ADSBexchange palette
// ═══════════════════════════════════════════════════════════════════════════════

const ALT_COLORS: [number, string][] = [
  [0,      "#737373"],  // ground — gray
  [100,    "#ff8c00"],  // orange
  [2000,   "#ffcc00"],  // yellow
  [5000,   "#00cc00"],  // green
  [10000,  "#00cccc"],  // cyan
  [20000,  "#0088ff"],  // blue
  [30000,  "#8800ff"],  // purple
  [40000,  "#ff0044"],  // red
  [55000,  "#ff0044"],  // red (cap)
];

function lerpColor(c1: string, c2: string, t: number): string {
  const parse = (hex: string) => [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
  const [r1, g1, b1] = parse(c1);
  const [r2, g2, b2] = parse(c2);
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);
  return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`;
}

export function getAltitudeColor(alt: number | "ground" | undefined | null): string {
  if (alt == null || alt === "ground" || alt <= 0) return ALT_COLORS[0][1];
  const feet = typeof alt === "number" ? alt : 0;
  for (let i = 1; i < ALT_COLORS.length; i++) {
    if (feet <= ALT_COLORS[i][0]) {
      const [lo, cLo] = ALT_COLORS[i - 1];
      const [hi, cHi] = ALT_COLORS[i];
      const t = (feet - lo) / (hi - lo);
      return lerpColor(cLo, cHi, t);
    }
  }
  return ALT_COLORS[ALT_COLORS.length - 1][1];
}

// ═══════════════════════════════════════════════════════════════════════════════
// Aircraft Icon Type Detection
// ═══════════════════════════════════════════════════════════════════════════════

export type IconType = "jet" | "turboprop" | "heli" | "fighter" | "heavy" | "ground" | "default";

// Common type code prefixes for classification
const FIGHTER_TYPES = new Set([
  "F15", "F16", "F18", "F22", "F35", "F14", "F4", "FA18",
  "EUFI", "RFAL", "GR4", "MIRAGE", "MIG", "SU27", "SU30", "SU35", "SU57",
  "J10", "J20", "F5", "F104", "F111", "TORNADO",
]);
const HEAVY_TYPES = new Set([
  "A380", "B747", "B748", "B77W", "B77L", "B772", "B773", "B789", "B78X",
  "A340", "A350", "C5", "C17", "C130", "C135", "KC10", "KC46", "KC135",
  "E3", "E6", "E8", "RC135", "P3", "P8", "AN124", "AN225", "IL76",
]);
const HELI_TYPES = new Set([
  "B06", "B407", "B412", "EC35", "EC45", "EC55", "EC75", "AS32", "AS50",
  "S76", "S92", "UH60", "AH64", "CH47", "V22", "MI8", "MI24", "MI26",
  "KA52", "R22", "R44", "R66", "A139", "A169", "A189", "NH90",
]);
const TURBOPROP_TYPES = new Set([
  "AT43", "AT45", "AT72", "AT76", "DH8A", "DH8B", "DH8C", "DH8D",
  "BE20", "BE30", "BE9L", "C208", "PC12", "TBM7", "TBM8", "TBM9",
  "E120", "J328", "SF34", "C295", "CN35",
]);

export function getIconType(ac: ADSBAircraft): IconType {
  const t = (ac.t ?? "").toUpperCase();
  const desc = (ac.desc ?? "").toUpperCase();
  const cat = ac.category ?? "";

  // Ground vehicle
  if (ac.alt_baro === "ground" && (cat.startsWith("C") || cat.startsWith("D"))) return "ground";

  // Helicopter
  if (cat === "A7" || desc.includes("H1") || desc.includes("H2") || desc.includes("H3")) return "heli";
  if (HELI_TYPES.has(t)) return "heli";

  // Fighter
  if (FIGHTER_TYPES.has(t)) return "fighter";
  if ((ac.dbFlags ?? 0) & 1 && desc.includes("J")) return "fighter"; // military + jet

  // Heavy
  if (HEAVY_TYPES.has(t)) return "heavy";
  if (cat === "A5" || cat === "A6") return "heavy"; // large + heavy emitter categories

  // Turboprop
  if (TURBOPROP_TYPES.has(t)) return "turboprop";
  if (desc.includes("T")) return "turboprop"; // desc contains T for turboprop

  // Jet (default for airborne non-turboprop)
  if (desc.includes("J") || cat === "A3" || cat === "A4") return "jet";

  return "default";
}

// ═══════════════════════════════════════════════════════════════════════════════
// SVG Aircraft Silhouettes
// ═══════════════════════════════════════════════════════════════════════════════

function svgSilhouette(type: IconType): string {
  switch (type) {
    case "jet":
      return `<path d="M0,-14 L2,-8 L2,-2 L8,4 L8,6 L2,3 L2,10 L5,13 L5,14 L0,12 L-5,14 L-5,13 L-2,10 L-2,3 L-8,6 L-8,4 L-2,-2 L-2,-8 Z"/>`;
    case "turboprop":
      return `<path d="M0,-12 L1.5,-6 L1.5,0 L9,5 L9,6 L1.5,4 L1.5,10 L4,12 L4,13 L0,11 L-4,13 L-4,12 L-1.5,10 L-1.5,4 L-9,6 L-9,5 L-1.5,0 L-1.5,-6 Z"/>
             <line x1="-7" y1="5" x2="7" y2="5" stroke-width="0.6" opacity="0.5"/>`;
    case "heli":
      return `<ellipse cx="0" cy="0" rx="4" ry="6"/>
              <line x1="0" y1="-6" x2="0" y2="-12" stroke-width="1"/>
              <line x1="-8" y1="-12" x2="8" y2="-12" stroke-width="1.2"/>
              <line x1="0" y1="6" x2="0" y2="12" stroke-width="0.8"/>
              <line x1="-3" y1="12" x2="3" y2="12" stroke-width="1"/>`;
    case "fighter":
      return `<path d="M0,-14 L3,-6 L3,0 L10,6 L10,5 L3,-1 L3,-6 L1.5,-10 L0,-14 L-1.5,-10 L-3,-6 L-3,-1 L-10,5 L-10,6 L-3,0 L-3,-6 Z"/>
              <path d="M0,8 L4,13 L4,14 L0,11 L-4,14 L-4,13 Z"/>`;
    case "heavy":
      return `<path d="M0,-16 L3,-10 L3,-2 L12,6 L12,8 L3,4 L3,12 L6,15 L6,16 L0,13 L-6,16 L-6,15 L-3,12 L-3,4 L-12,8 L-12,6 L-3,-2 L-3,-10 Z"/>`;
    case "ground":
      return `<rect x="-6" y="-6" width="12" height="12" rx="2"/>
              <circle cx="-4" cy="6" r="2"/>
              <circle cx="4" cy="6" r="2"/>`;
    default: // GA / default
      return `<path d="M0,-10 L1.5,-5 L1.5,0 L7,4 L7,5 L1.5,3 L1.5,9 L4,11 L4,12 L0,10 L-4,12 L-4,11 L-1.5,9 L-1.5,3 L-7,5 L-7,4 L-1.5,0 L-1.5,-5 Z"/>`;
  }
}

export function createAircraftSvg(
  type: IconType,
  heading: number,
  color: string,
  size: number,
  selected: boolean,
): string {
  const half = size / 2;
  const glow = selected
    ? `<circle cx="0" cy="0" r="16" fill="none" stroke="#ffffff" stroke-width="2" opacity="0.6"/>
       <circle cx="0" cy="0" r="16" fill="none" stroke="#ffffff" stroke-width="0.5" opacity="0.3"/>`
    : "";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="-${half} -${half} ${size} ${size}">
    <g transform="rotate(${heading ?? 0})" fill="${color}" stroke="${color}" stroke-width="0.3">
      ${glow}
      ${svgSilhouette(type)}
    </g>
  </svg>`;
  return "data:image/svg+xml;base64," + btoa(svg);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Hooks
// ═══════════════════════════════════════════════════════════════════════════════

interface UseAircraftDataOptions {
  lat?: number;
  lon?: number;
  radiusNm?: number;
  icaoFilter?: string[];
  pollInterval?: number;
  enabled?: boolean;
}

export function useAircraftData(opts: UseAircraftDataOptions) {
  const {
    lat, lon, radiusNm = 150,
    icaoFilter,
    pollInterval = 5000,
    enabled = true,
  } = opts;

  const [aircraft, setAircraft] = useState<ADSBAircraft[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<number>(0);
  const abortRef = useRef<AbortController | null>(null);

  const fetchAircraft = useCallback(async () => {
    if (!enabled) return;
    try {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      let results: ADSBAircraft[] = [];

      if (icaoFilter && icaoFilter.length > 0) {
        // Fetch individual aircraft by hex
        const fetches = icaoFilter.map(async (hex) => {
          const res = await apiFetch(`${ADSB_API}/v2/hex/${hex}`, { signal: ac.signal });
          if (!res.ok) return [];
          const data: ADSBResponse = await res.json();
          return data.ac ?? [];
        });
        const all = await Promise.all(fetches);
        results = all.flat();
      } else if (lat != null && lon != null) {
        const res = await apiFetch(
          `${ADSB_API}/v2/lat/${lat}/lon/${lon}/dist/${radiusNm}`,
          { signal: ac.signal },
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: ADSBResponse = await res.json();
        results = data.ac ?? [];
      }

      // Filter out stale aircraft
      const now = nowMs() / 1000;
      results = results.filter(
        (a) => a.lat != null && a.lon != null && (a.seen_pos == null || a.seen_pos < STALE_TIMEOUT_S),
      );

      setAircraft(results);
      setLastUpdate(nowMs());
      setError(null);
    } catch (e: any) {
      if (e.name !== "AbortError") {
        setError(e.message ?? "Fetch failed");
      }
    }
  }, [enabled, lat, lon, radiusNm, icaoFilter]);

  useEffect(() => {
    fetchAircraft();
    const id = setInterval(fetchAircraft, pollInterval);
    return () => {
      clearInterval(id);
      abortRef.current?.abort();
    };
  }, [fetchAircraft, pollInterval]);

  return { aircraft, error, lastUpdate, refetch: fetchAircraft };
}

// ── Track History Hook ──────────────────────────────────────────────────────

export function useTrackHistory(
  aircraft: ADSBAircraft[],
  maxPoints: number = 60,
): Map<string, TrackPoint[]> {
  const historyRef = useRef<Map<string, TrackPoint[]>>(new Map());
  const lastSeenRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    const now = nowMs();
    const hist = historyRef.current;
    const lastSeen = lastSeenRef.current;

    // Update tracks
    for (const ac of aircraft) {
      if (ac.lat == null || ac.lon == null) continue;
      const trail = hist.get(ac.hex) ?? [];
      const last = trail[trail.length - 1];
      // Only add point if position actually changed
      if (!last || last.lat !== ac.lat || last.lon !== ac.lon) {
        trail.push({
          lat: ac.lat,
          lon: ac.lon,
          alt: ac.alt_baro ?? 0,
          ts: now,
        });
        if (trail.length > maxPoints) trail.splice(0, trail.length - maxPoints);
        hist.set(ac.hex, trail);
      }
      lastSeen.set(ac.hex, now);
    }

    // Prune stale aircraft
    for (const [hex, ts] of lastSeen) {
      if (now - ts > STALE_TIMEOUT_S * 1000) {
        hist.delete(hex);
        lastSeen.delete(hex);
      }
    }
  }, [aircraft, maxPoints]);

  return historyRef.current;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter Logic
// ═══════════════════════════════════════════════════════════════════════════════

export function applyFilters(aircraft: ADSBAircraft[], filters: AircraftFilters): ADSBAircraft[] {
  return aircraft.filter((ac) => {
    if (filters.callsign) {
      try {
        const re = new RegExp(filters.callsign, "i");
        if (!re.test(ac.flight?.trim() ?? "")) return false;
      } catch { return false; }
    }
    if (filters.typeCode) {
      try {
        const re = new RegExp(filters.typeCode, "i");
        if (!re.test(ac.t ?? "")) return false;
      } catch { return false; }
    }
    if (filters.squawk) {
      if (ac.squawk !== filters.squawk) return false;
    }
    if (filters.altMin != null) {
      const alt = typeof ac.alt_baro === "number" ? ac.alt_baro : -1;
      if (alt < filters.altMin) return false;
    }
    if (filters.altMax != null) {
      const alt = typeof ac.alt_baro === "number" ? ac.alt_baro : 999999;
      if (alt > filters.altMax) return false;
    }
    if (filters.militaryOnly) {
      if (!((ac.dbFlags ?? 0) & 1)) return false;
    }
    return true;
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// UI Components
// ═══════════════════════════════════════════════════════════════════════════════

const PANEL_BG = "rgba(6,10,15,0.95)";
const PANEL_BORDER = "rgba(88,166,255,0.2)";
const MONO = "var(--font-mono), 'JetBrains Mono', monospace";
const DIM = "#5a6a7e";
const BRIGHT = "#c8d6e5";

// ── Filter Bar (right sidebar) ──────────────────────────────────────────────

interface FilterBarProps {
  filters: AircraftFilters;
  onFilterChange: (f: AircraftFilters) => void;
  totalCount: number;
  filteredCount: number;
  visible: boolean;
  onToggle: () => void;
}

export function FilterBar({ filters, onFilterChange, totalCount, filteredCount, visible, onToggle }: FilterBarProps) {
  const set = (key: keyof AircraftFilters, val: any) =>
    onFilterChange({ ...filters, [key]: val || undefined });

  return (
    <div style={{
      position: "absolute", top: 10, right: 10, zIndex: 1002,
      fontFamily: MONO, fontSize: 11, pointerEvents: "none",
      display: "flex", flexDirection: "column", gap: 0,
    }}>
      <button
        onClick={onToggle}
        style={{
          background: PANEL_BG, border: `1px solid ${PANEL_BORDER}`,
          borderRadius: visible ? "3px 3px 0 0" : 3,
          color: "#58a6ff", padding: "4px 10px", cursor: "pointer",
          fontSize: 11, letterSpacing: 1.5, fontFamily: MONO,
          display: "flex", alignItems: "center", gap: 6,
          pointerEvents: "auto",
        }}
      >
        <span style={{ fontSize: 11 }}>✈</span>
        ADSB FILTER
        <span style={{ color: DIM, fontSize: 11 }}>{filteredCount}/{totalCount}</span>
      </button>

      {visible && (
        <div style={{
          background: PANEL_BG, border: `1px solid ${PANEL_BORDER}`,
          borderTop: "none", borderRadius: "0 0 3px 3px",
          padding: "10px 12px", minWidth: 180,
          display: "flex", flexDirection: "column", gap: 8,
          pointerEvents: "auto",
        }}>
          {/* Callsign */}
          <label style={{ color: DIM, fontSize: 11, letterSpacing: 1 }}>
            CALLSIGN (REGEX)
            <input
              type="text"
              value={filters.callsign ?? ""}
              onChange={(e) => set("callsign", e.target.value)}
              placeholder="e.g. RCH|DUKE"
              style={inputStyle}
            />
          </label>

          {/* Type Code */}
          <label style={{ color: DIM, fontSize: 11, letterSpacing: 1 }}>
            TYPE CODE (REGEX)
            <input
              type="text"
              value={filters.typeCode ?? ""}
              onChange={(e) => set("typeCode", e.target.value)}
              placeholder="e.g. B73.|A32."
              style={inputStyle}
            />
          </label>

          {/* Squawk */}
          <label style={{ color: DIM, fontSize: 11, letterSpacing: 1 }}>
            SQUAWK
            <input
              type="text"
              value={filters.squawk ?? ""}
              onChange={(e) => set("squawk", e.target.value)}
              placeholder="e.g. 7700"
              style={inputStyle}
            />
          </label>

          {/* Altitude range */}
          <div style={{ display: "flex", gap: 6 }}>
            <label style={{ color: DIM, fontSize: 11, letterSpacing: 1, flex: 1 }}>
              ALT MIN (FT)
              <input
                type="number"
                value={filters.altMin ?? ""}
                onChange={(e) => set("altMin", e.target.value ? Number(e.target.value) : undefined)}
                style={inputStyle}
              />
            </label>
            <label style={{ color: DIM, fontSize: 11, letterSpacing: 1, flex: 1 }}>
              ALT MAX (FT)
              <input
                type="number"
                value={filters.altMax ?? ""}
                onChange={(e) => set("altMax", e.target.value ? Number(e.target.value) : undefined)}
                style={inputStyle}
              />
            </label>
          </div>

          {/* Military only */}
          <label style={{
            display: "flex", alignItems: "center", gap: 7,
            cursor: "pointer", userSelect: "none", color: BRIGHT, fontSize: 11,
          }}>
            <div style={{
              width: 10, height: 10,
              background: filters.militaryOnly ? "#ff404044" : "transparent",
              border: "1.5px solid #ff4040",
              borderRadius: 2, flexShrink: 0,
            }}
              onClick={() => set("militaryOnly", !filters.militaryOnly)}
            />
            <span onClick={() => set("militaryOnly", !filters.militaryOnly)}>
              MILITARY ONLY
            </span>
          </label>

          {/* Clear */}
          <button
            onClick={() => onFilterChange({})}
            style={{
              background: "transparent", border: `1px solid ${PANEL_BORDER}`,
              borderRadius: 2, color: DIM, padding: "3px 8px",
              cursor: "pointer", fontSize: 11, fontFamily: MONO,
              letterSpacing: 1,
            }}
          >
            CLEAR FILTERS
          </button>
        </div>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  display: "block", width: "100%", marginTop: 3,
  background: "rgba(255,255,255,0.05)", border: `1px solid ${PANEL_BORDER}`,
  borderRadius: 2, color: BRIGHT, padding: "3px 6px",
  fontSize: 11, fontFamily: MONO, outline: "none",
};

// ── Aircraft Detail Panel (left sidebar) ────────────────────────────────────

interface AircraftDetailPanelProps {
  aircraft: ADSBAircraft | null;
  onClose: () => void;
}

export function AircraftDetailPanel({ aircraft: ac, onClose }: AircraftDetailPanelProps) {
  if (!ac) return null;

  const altBaro = typeof ac.alt_baro === "number" ? ac.alt_baro.toLocaleString() + " ft" : (ac.alt_baro === "ground" ? "GROUND" : "N/A");
  const altGeom = ac.alt_geom != null ? ac.alt_geom.toLocaleString() + " ft" : "N/A";
  const altColor = getAltitudeColor(ac.alt_baro);
  const isMilitary = (ac.dbFlags ?? 0) & 1;
  const isEmergency = ac.emergency && ac.emergency !== "none";
  const emergSquawk = ac.squawk ? EMERGENCY_SQUAWKS[ac.squawk] : undefined;
  const vrColor = (ac.baro_rate ?? 0) > 0 ? "#3fb950" : (ac.baro_rate ?? 0) < 0 ? "#f85149" : DIM;

  return (
    <div style={{
      position: "absolute", top: 10, left: 10, zIndex: 1003,
      background: PANEL_BG, border: `1px solid ${PANEL_BORDER}`,
      borderRadius: 3, padding: "12px 14px",
      fontFamily: MONO, fontSize: 11, color: BRIGHT,
      minWidth: 240, maxWidth: 280, maxHeight: "calc(100% - 20px)",
      overflowY: "auto", pointerEvents: "auto",
      boxShadow: "0 0 30px rgba(0,0,0,0.6)",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: altColor }}>
            {ac.flight?.trim() || ac.hex.toUpperCase()}
          </span>
          {isMilitary ? (
            <span style={{ fontSize: 11, padding: "1px 5px", borderRadius: 2, fontWeight: 700,
              background: "#ff404022", color: "#ff4040", border: "1px solid #ff404044",
              letterSpacing: 0.5 }}>MIL</span>
          ) : null}
          {isEmergency ? (
            <span style={{ fontSize: 11, padding: "1px 5px", borderRadius: 2, fontWeight: 700,
              background: "#ff404033", color: "#ff4040", border: "1px solid #ff4040",
              letterSpacing: 0.5, animation: "acEmergencyFlash 0.7s ease-in-out infinite" }}>
              EMERGENCY
            </span>
          ) : null}
        </div>
        <button onClick={onClose} style={{
          background: "transparent", border: "none", color: DIM,
          cursor: "pointer", fontSize: 14, lineHeight: 1, padding: "0 2px",
        }}>×</button>
      </div>

      {/* Emergency banner */}
      {emergSquawk && (
        <div style={{
          background: emergSquawk.color + "22", border: `1px solid ${emergSquawk.color}`,
          borderRadius: 2, padding: "4px 8px", marginBottom: 8,
          color: emergSquawk.color, fontWeight: 700, fontSize: 11, textAlign: "center",
        }}>
          ⚠ SQUAWK {ac.squawk} — {emergSquawk.label}
        </div>
      )}

      {/* Fields */}
      <div style={{ display: "flex", flexDirection: "column", gap: 3, lineHeight: 1.8 }}>
        <Row label="ICAO" value={ac.hex.toUpperCase()} />
        {ac.r && <Row label="Registration" value={ac.r} />}
        {ac.t && <Row label="Type" value={`${ac.t}${ac.desc ? ` (${ac.desc})` : ""}`} />}
        {ac.squawk && !emergSquawk && <Row label="Squawk" value={ac.squawk} />}
        <Row label="Alt (baro)" value={altBaro} valueColor={altColor} />
        <Row label="Alt (geom)" value={altGeom} />
        {ac.gs != null && <Row label="GS" value={Math.round(ac.gs) + " kts"} />}
        {ac.ias != null && <Row label="IAS" value={ac.ias + " kts"} />}
        {ac.tas != null && <Row label="TAS" value={ac.tas + " kts"} />}
        {ac.mach != null && <Row label="Mach" value={ac.mach.toFixed(3)} />}
        {ac.track != null && <Row label="Track" value={Math.round(ac.track) + "°"} />}
        {ac.baro_rate != null && (
          <Row label="V/S" value={`${ac.baro_rate > 0 ? "▲" : ac.baro_rate < 0 ? "▼" : "—"} ${Math.abs(ac.baro_rate).toLocaleString()} fpm`} valueColor={vrColor} />
        )}
        {ac.lat != null && ac.lon != null && (
          <Row label="Position" value={`${ac.lat.toFixed(4)}°, ${ac.lon.toFixed(4)}°`} />
        )}
        {ac.nav_altitude_mcp != null && <Row label="Sel Alt" value={ac.nav_altitude_mcp.toLocaleString() + " ft"} />}
        {ac.nav_heading != null && <Row label="Sel Hdg" value={Math.round(ac.nav_heading) + "°"} />}
        {ac.rssi != null && <Row label="RSSI" value={ac.rssi.toFixed(1) + " dBFS"} />}
        {ac.type && <Row label="Source" value={ac.type} />}
        {ac.category && <Row label="Category" value={ac.category} />}
        {ac.seen != null && <Row label="Last seen" value={ac.seen.toFixed(1) + "s ago"} />}
      </div>

      {/* External links */}
      <div style={{ marginTop: 10, paddingTop: 8, borderTop: `1px solid ${PANEL_BORDER}`,
        display: "flex", gap: 8, flexWrap: "wrap", fontSize: 11 }}>
        <ExtLink href={`https://globe.adsbexchange.com/?icao=${ac.hex}`} label="ADSBx" />
        <ExtLink href={`https://globe.adsb.lol/?icao=${ac.hex}`} label="adsb.lol" />
        {ac.r && <ExtLink href={`https://flightaware.com/live/flight/${ac.r}`} label="FlightAware" />}
        {ac.flight && <ExtLink href={`https://www.flightradar24.com/${ac.flight.trim()}`} label="FR24" />}
      </div>

      <div style={{ marginTop: 8, fontSize: 11, color: "#8b9eaf" }}>
        Source: adsb.lol V2 API · {ac.type ?? "adsb"}
      </div>
    </div>
  );
}

function Row({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div style={{ color: DIM }}>
      {label}: <span style={{ color: valueColor ?? BRIGHT }}>{value}</span>
    </div>
  );
}

function ExtLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer"
      style={{ color: "#58a6ff", textDecoration: "none", padding: "2px 6px",
        border: `1px solid ${PANEL_BORDER}`, borderRadius: 2 }}>
      {label} ↗
    </a>
  );
}

// ── Aircraft Table (bottom panel) ───────────────────────────────────────────

interface AircraftTableProps {
  aircraft: ADSBAircraft[];
  onSelect: (ac: ADSBAircraft) => void;
  selectedHex?: string | null;
  visible: boolean;
  onToggle: () => void;
}

type SortKey = "flight" | "t" | "alt_baro" | "gs" | "squawk" | "baro_rate";
type SortDir = "asc" | "desc";

export function AircraftTable({ aircraft, onSelect, selectedHex, visible, onToggle }: AircraftTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("alt_baro");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("desc"); }
  };

  const sorted = useMemo(() => {
    return [...aircraft].sort((a, b) => {
      let av: any, bv: any;
      switch (sortKey) {
        case "flight": av = a.flight?.trim() ?? ""; bv = b.flight?.trim() ?? ""; break;
        case "t": av = a.t ?? ""; bv = b.t ?? ""; break;
        case "alt_baro":
          av = typeof a.alt_baro === "number" ? a.alt_baro : -1;
          bv = typeof b.alt_baro === "number" ? b.alt_baro : -1;
          break;
        case "gs": av = a.gs ?? 0; bv = b.gs ?? 0; break;
        case "squawk": av = a.squawk ?? ""; bv = b.squawk ?? ""; break;
        case "baro_rate": av = a.baro_rate ?? 0; bv = b.baro_rate ?? 0; break;
      }
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [aircraft, sortKey, sortDir]);

  const arrow = (key: SortKey) => sortKey === key ? (sortDir === "asc" ? " ▲" : " ▼") : "";

  return (
    <div style={{
      position: "absolute", bottom: 0, left: 0, right: 0, zIndex: 1002,
      fontFamily: MONO, fontSize: 11, pointerEvents: "none",
    }}>
      <button
        onClick={onToggle}
        style={{
          background: PANEL_BG, border: `1px solid ${PANEL_BORDER}`,
          borderBottom: visible ? "none" : `1px solid ${PANEL_BORDER}`,
          borderRadius: visible ? "3px 3px 0 0" : 3,
          color: "#58a6ff", padding: "3px 10px", cursor: "pointer",
          fontSize: 11, letterSpacing: 1.5, fontFamily: MONO,
          marginLeft: 10, pointerEvents: "auto",
        }}
      >
        {visible ? "▼" : "▲"} AIRCRAFT TABLE ({aircraft.length})
      </button>

      {visible && (
        <div style={{
          background: PANEL_BG, border: `1px solid ${PANEL_BORDER}`,
          borderTop: "none", maxHeight: 200, overflowY: "auto",
          pointerEvents: "auto",
        }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: DIM, fontSize: 11, letterSpacing: 1, position: "sticky", top: 0, background: PANEL_BG }}>
                {(
                  [
                    ["flight", "CALLSIGN"],
                    ["t", "TYPE"],
                    ["alt_baro", "ALT"],
                    ["gs", "GS"],
                    ["baro_rate", "V/S"],
                    ["squawk", "SQK"],
                  ] as [SortKey, string][]
                ).map(([key, label]) => (
                  <th key={key}
                    onClick={() => toggleSort(key)}
                    style={{ padding: "4px 6px", cursor: "pointer", textAlign: "left",
                      borderBottom: `1px solid ${PANEL_BORDER}`, userSelect: "none", whiteSpace: "nowrap" }}>
                    {label}{arrow(key)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((ac) => {
                const altNum = typeof ac.alt_baro === "number" ? ac.alt_baro : null;
                const altColor = getAltitudeColor(ac.alt_baro);
                const emergSqk = ac.squawk ? EMERGENCY_SQUAWKS[ac.squawk] : undefined;
                const vrColor = (ac.baro_rate ?? 0) > 0 ? "#3fb950" : (ac.baro_rate ?? 0) < 0 ? "#f85149" : DIM;
                const isSel = ac.hex === selectedHex;
                return (
                  <tr key={ac.hex}
                    onClick={() => onSelect(ac)}
                    style={{
                      cursor: "pointer",
                      background: isSel ? "rgba(88,166,255,0.1)" : "transparent",
                      borderBottom: `1px solid rgba(88,166,255,0.05)`,
                    }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "rgba(88,166,255,0.08)"; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = isSel ? "rgba(88,166,255,0.1)" : "transparent"; }}
                  >
                    <td style={{ padding: "3px 6px", color: (ac.dbFlags ?? 0) & 1 ? "#ff4040" : BRIGHT }}>
                      {ac.flight?.trim() || ac.hex.toUpperCase()}
                    </td>
                    <td style={{ padding: "3px 6px", color: DIM }}>{ac.t ?? ""}</td>
                    <td style={{ padding: "3px 6px", color: altColor }}>
                      {altNum != null ? altNum.toLocaleString() : (ac.alt_baro === "ground" ? "GND" : "")}
                    </td>
                    <td style={{ padding: "3px 6px", color: BRIGHT }}>
                      {ac.gs != null ? Math.round(ac.gs) : ""}
                    </td>
                    <td style={{ padding: "3px 6px", color: vrColor }}>
                      {ac.baro_rate != null ? `${ac.baro_rate > 0 ? "+" : ""}${ac.baro_rate.toLocaleString()}` : ""}
                    </td>
                    <td style={{ padding: "3px 6px", color: emergSqk ? emergSqk.color : DIM, fontWeight: emergSqk ? 700 : 400 }}>
                      {ac.squawk ?? ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
