import { severityLabel } from "../lib/events";
import { SHOWCASE, safeUrl } from "../lib/runtime";
import { sanitizeHtml, escapeHtml } from "../lib/html";
import { apiFetch } from "../lib/api";
/**
 * MapPanel.tsx — Tactical Intelligence Display (2D Only)
 *
 * Features:
 *  - Tactical pulse-ring event markers with severity tiers
 *  - Intelligence-report popups
 *  - Category filter panel (event types + infrastructure layers)
 *  - Infrastructure: refineries, airfields, oil/gas pipelines
 *  - Military bases, chokepoints, aircraft, vessels, GPS jamming
 */

import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { ConflictEvent } from "../types/event";
import { hasMultipleReports, isViralAmplification, getNetworks, NETWORK_META } from "../utils/verification";
import type { Aircraft, JammingZone, TLERecord, Vessel } from "../hooks/useTracking";
import {
  type ADSBAircraft, type AircraftFilters,
  getAltitudeColor, getIconType, createAircraftSvg,
  applyFilters as applyADSBFilters,
  useAircraftData, useTrackHistory,
  AircraftDetailPanel,
} from "./AircraftLayer";

// ── Conflict zone bounding box ───────────────────────────────────────────────
const CONFLICT_BOX = { latMin: 8, latMax: 42, lonMin: 28, lonMax: 67 };

function safeDivIcon(options: L.DivIconOptions) {
  return L.divIcon({...options, html: typeof options.html === "string" ? sanitizeHtml(options.html) : options.html});
}

// Commercial airline ICAO prefixes — filtered from tactical display
const AIRLINE_PREFIXES = new Set([
  "AAL","UAL","DAL","SWA","BAW","AFR","DLH","KLM","UAE","QTR","THY","SVA",
  "ETH","MSR","RYR","EZY","IBE","TAP","AZA","SAS","FIN","LOT","CSN","CCA",
  "CES","CHH","AIC","JAL","ANA","KAL","AAR","MAS","SIA","THA","GFA","OMA",
  "ELY","ROT","BMS","PIA","IRA","IRM","IRB","FZA","MEA","GLL","RAM","TUN",
  "AMC","AMF","AMX","AXM","AEA","AVA","GLO","LAM","LNE","LPE","TAM","VRG",
  "EIA","FDB","FLY","JZR","NAS","PGT","RJA","TCX","TOM","TUI","WZZ","EXS",
]);

function isInterestingCallsign(callsign: string): boolean {
  if (!callsign || callsign.trim().length === 0) return true;
  const cs = callsign.trim().toUpperCase();
  if (AIRLINE_PREFIXES.has(cs.slice(0, 3))) return false;
  if (/^\d+$/.test(cs)) return false;
  return true;
}

// ── Aircraft classification colors ──────────────────────────────────────────
const AC_CAT_COLORS: Record<string, string> = {
  military:     "#ff4040",
  surveillance: "#a855f7",
  tanker:       "#f59e0b",
  cargo:        "#f59e0b",
  uav:          "#fb923c",
  helicopter:   "#facc15",
  civilian:     "#58d0ff",
};
const AC_CAT_LABELS: Record<string, string> = {
  military:     "MILITARY",
  surveillance: "ISR/SIGINT",
  tanker:       "TANKER",
  cargo:        "MIL CARGO",
  uav:          "UAV/DRONE",
  helicopter:   "HELICOPTER",
  civilian:     "CIVILIAN",
};
function acColor(ac: import("../hooks/useTracking").Aircraft): string {
  if (ac.is_emergency) return "#ff4040";
  return AC_CAT_COLORS[ac.aircraft_category ?? "civilian"] ?? "#58d0ff";
}
function formatSquawk(sq: string | undefined): string {
  if (!sq) return "";
  if (sq === "7700") return `<span style="color:#ff4040;font-weight:700;">7700 MAYDAY</span>`;
  if (sq === "7600") return `<span style="color:#f59e0b;font-weight:700;">7600 RADIO FAIL</span>`;
  if (sq === "7500") return `<span style="color:#ff4040;font-weight:700;">7500 HIJACK</span>`;
  return sq;
}

// Leaflet 1.9 Canvas._updatePaths may call _redraw synchronously while its
// earlier RAF is pending. The stock _redraw clears the ID without cancelling
// that callback, so onRemove can no longer cancel it. Cancel the owned request
// before every redraw; do not swallow renderer errors or skip live rendering.
const OwnedFrameCanvas=L.Canvas.extend({
  _redraw(this:L.Canvas & {_redrawRequest?:number}){
    if(this._redrawRequest!=null)L.Util.cancelAnimFrame(this._redrawRequest);
    (L.Canvas.prototype as any)._redraw.call(this);
  },
}) as new()=>L.Canvas;

// ── Event type config ────────────────────────────────────────────────────────
const EVENT_TYPE_CONFIG: Record<string, { color: string; label: string; icon: string }> = {
  unclassified: {color:"#91b4c5",label:"Source report",icon:"▤"},
  military:     { color: "#f85149", label: "Military",     icon: "💥" },
  diplomatic:   { color: "#58a6ff", label: "Diplomatic",   icon: "🏛" },
  economic:     { color: "#d29922", label: "Economic",     icon: "📈" },
  cyber:        { color: "#bc8cff", label: "Cyber",        icon: "⚡" },
  humanitarian: { color: "#3fb950", label: "Humanitarian", icon: "🚑" },
  protest:         { color: "#f0883e", label: "Protest",      icon: "✊" },
  thermal_anomaly: { color: "#ff8800", label: "Thermal",      icon: "🔥" },
};
const EVENT_COLORS = Object.fromEntries(
  Object.entries(EVENT_TYPE_CONFIG).map(([k, v]) => [k, v.color])
) as Record<string, string>;

// ── Military subtype detection (from summary text) ────────────────────────────
type MilSubtype = "airstrike" | "missile" | "drone" | "naval" | "artillery" | "ground" | "assassination" | "default";
const MIL_SUBTYPE_LABELS: Record<MilSubtype, string> = {
  airstrike:    "Airstrike",
  missile:      "Missile/Ballistic",
  drone:        "Drone/UAV",
  naval:        "Naval Attack",
  artillery:    "Artillery/Rocket",
  ground:       "Ground Assault",
  assassination:"Targeted Killing",
  default:      "Military",
};
function getMilSubtype(summary: string): MilSubtype {
  const s = (summary || "").toLowerCase();
  if (/drone|uav|shahed|loiter|unmanned aerial/.test(s))                      return "drone";
  if (/ballistic|cruise missile|hypersonic|bmd|scud|fateh|kh-101/.test(s))    return "missile";
  if (/airstrike|air strike|bombing|warplane|f-15|f-35|f-16|jet|aircraft.{0,20}attack|bomb/.test(s)) return "airstrike";
  if (/naval|ship|vessel|frigate|destroyer|carrier|submarine|tanker.{0,20}attack|sea-based/.test(s)) return "naval";
  if (/artillery|shelling|rocket fire|mortar|barrage|katyusha|grad/.test(s))  return "artillery";
  if (/ground|infantry|troops|armored|invasion|incursion|cross.{0,10}border|tank/.test(s)) return "ground";
  if (/assassin|targeted killing|killed|eliminat|liquidat/.test(s))           return "assassination";
  return "default";
}

// Returns the SVG overlay path/shape that visually identifies a military subtype
function milSubtypeOverlay(subtype: MilSubtype): string {
  switch (subtype) {
    case "airstrike":    // Downward-pointing chevron (incoming from above)
      return `<path d="M0,-5 L3.5,2 L0,0 L-3.5,2 Z" fill="rgba(255,255,255,0.85)" stroke="none"/>`;
    case "missile":      // Upward arrow (missile launch)
      return `<path d="M0,-6 L0,3 M-2,-3 L0,-6 L2,-3" stroke="rgba(255,255,255,0.9)" stroke-width="1.1" fill="none" stroke-linecap="round"/>`;
    case "drone":        // Target ring
      return `<circle cx="0" cy="0" r="4.5" fill="none" stroke="rgba(255,255,255,0.85)" stroke-width="0.9"/>
              <circle cx="0" cy="0" r="1.2" fill="rgba(255,255,255,0.9)"/>`;
    case "naval":        // Horizontal wave line (sea)
      return `<path d="M-5,1.5 C-3,-1 -1,3.5 0,1 C1,-1 3,3.5 5,1" stroke="rgba(255,255,255,0.85)" stroke-width="1" fill="none"/>`;
    case "artillery":    // Three radiating dashes
      return `<line x1="-5" y1="0" x2="-2.5" y2="0" stroke="rgba(255,255,255,0.85)" stroke-width="1.1"/>
              <line x1="2.5" y1="0" x2="5" y2="0" stroke="rgba(255,255,255,0.85)" stroke-width="1.1"/>
              <line x1="0" y1="-5" x2="0" y2="-2.5" stroke="rgba(255,255,255,0.85)" stroke-width="1.1"/>`;
    case "ground":       // Bold X
      return `<path d="M-4,-4 L4,4 M4,-4 L-4,4" stroke="rgba(255,255,255,0.85)" stroke-width="1.2" stroke-linecap="round"/>`;
    case "assassination": // Target crosshair
      return `<circle cx="0" cy="0" r="3.5" fill="none" stroke="rgba(255,255,255,0.8)" stroke-width="0.8"/>
              <line x1="-5.5" y1="0" x2="5.5" y2="0" stroke="rgba(255,255,255,0.8)" stroke-width="0.8"/>
              <line x1="0" y1="-5.5" x2="0" y2="5.5" stroke="rgba(255,255,255,0.8)" stroke-width="0.8"/>`;
    default:             // White center dot only
      return ``;
  }
}

// ── Source name friendly mapping ───────────────────────────────────────────────
const SOURCE_NAMES: Record<string, string> = {
  rss_reuters:          "Reuters",
  rss_bbc_mideast:      "BBC Middle East",
  rss_ap_news:          "AP News",
  rss_the_war_zone:     "The War Zone",
  rss_aljazeera:        "Al Jazeera",
  rss_times_of_israel:  "Times of Israel",
  rss_iran_international: "Iran International",
  rss_rfi:              "France RFI",
  rss_defense_one:      "Defense One",
  rss_france24:         "France 24",
  rss_jerusalem_post:   "Jerusalem Post",
  rss_new_arab:         "The New Arab",
  rss_sky_news_me:      "Sky News ME",
  telegram:             "Telegram",
};

// ── Reliability helpers ───────────────────────────────────────────────────────
function relLabel(score: number | null | undefined): string {
  return score == null ? "SOURCE RATING UNASSESSED" : `LEGACY SOURCE RATING ${score}/5 · NOT CLAIM VERIFICATION`;
}
function relColor(score: number | null | undefined): string {
  if (!score) return "#7a8b9a";
  if (score >= 5) return "#3fb950";
  if (score >= 4) return "#58a6ff";
  if (score >= 3) return "#d29922";
  if (score >= 2) return "#f0883e";
  return "#f85149";
}
function sevColor(s: number): string {
  if (s <= 3) return "#3fb950";
  if (s <= 6) return "#d29922";
  return "#f85149";
}

// ── Tactical CSS ──────────────────────────────────────────────────────────────
const TACTICAL_CSS = `
@keyframes conflictPulse {
  0% { transform: scale(1); opacity: 0.8; }
  50% { transform: scale(1.4); opacity: 0.3; }
  100% { transform: scale(1.8); opacity: 0; }
}
.leaflet-container { background: #0a0e14 !important; }
/* Smooth tile fade-in to eliminate grid pop-in during zoom */
.leaflet-tile-container img { transition: opacity 0.25s ease-in-out; }
/* Satellite base — subtle darken to help markers pop while keeping terrain vivid */
.tac-imagery-base { filter: brightness(0.82) saturate(0.85) contrast(1.05); }
/* Reference label layer — crisp country names and borders */
.tac-imagery-ref  { filter: brightness(1.2) contrast(1.15); opacity: 0.95; }
.leaflet-popup-content-wrapper {
  background: rgba(6,10,15,0.97) !important;
  border: 1px solid rgba(88,166,255,0.25) !important;
  border-radius: 3px !important;
  box-shadow: 0 0 20px rgba(0,0,0,0.8), 0 0 40px rgba(88,166,255,0.05) !important;
  padding: 0 !important;
}
.leaflet-popup-tip { background: rgba(6,10,15,0.97) !important; }
.leaflet-popup-content { margin: 0 !important; }
/* Let the map receive drag events through the popup's transparent region */
.leaflet-popup { pointer-events: none !important; }
.leaflet-popup-content-wrapper,
.leaflet-popup-close-button { pointer-events: auto !important; }
.leaflet-popup-close-button {
  color: #5a6a7e !important;
  font-size: 14px !important;
  top: 6px !important; right: 8px !important;
}
.leaflet-popup-close-button:hover { color: #c8d6e5 !important; }
.leaflet-control-attribution {
  background: rgba(6,10,15,0.7) !important;
  color: #8b9eaf !important;
  font-size: 11px !important;
}
.leaflet-control-attribution a { color: #8ea8be !important; }
.leaflet-control-zoom a {
  background: rgba(10,14,20,0.9) !important;
  border-color: rgba(88,166,255,0.2) !important;
  color: #58a6ff !important;
}
.leaflet-control-zoom a:hover { background: rgba(88,166,255,0.15) !important; }

/* Pulse ring animations */
@keyframes tacNewEvent {
  0%   { transform: scale(0.2); opacity: 0; }
  60%  { transform: scale(1.4); opacity: 1; }
  100% { transform: scale(1);   opacity: 1; }
}
@keyframes tacCritBlink {
  0%,100% { opacity: 1; }
  50%      { opacity: 0.25; }
}
.tac-new { animation: tacNewEvent 0.5s ease forwards; }
.tac-crit { animation: tacCritBlink 0.9s ease-in-out infinite; }
@keyframes acEmergencyFlash { 0%,100% { opacity:1; } 50% { opacity:0.2; } }
.ac-emergency { animation: acEmergencyFlash 0.7s ease-in-out infinite; }
/* Kill browser focus ring on all Leaflet marker elements */
.leaflet-marker-icon, .leaflet-marker-icon:focus, .leaflet-marker-icon *, .leaflet-div-icon { outline: none !important; box-shadow: none !important; border: none !important; background: transparent !important; }
.leaflet-interactive:focus { outline: none !important; }
`;

// ── Vessel type color mapping (AIS ship_type integer codes + name fallback) ───
const VESSEL_CAT_COLORS: Record<string, string> = {
  naval:      "#ff4040",   // red — military/warship
  government: "#a855f7",   // purple — coast guard / law enforcement
  tanker:     "#e53e3e",   // dark red
  cargo:      "#38a169",   // green
  passenger:  "#4299e1",   // blue
  fishing:    "#00bcd4",   // cyan
  high_speed: "#ed8936",   // amber
  tug:        "#ed8936",   // amber
  other:      "#718096",   // slate
};
const VESSEL_CAT_LABELS: Record<string, string> = {
  naval:      "NAVAL",
  government: "GOVT/COAST GUARD",
  tanker:     "TANKER",
  cargo:      "CARGO",
  passenger:  "PASSENGER",
  fishing:    "FISHING",
  high_speed: "HIGH SPEED",
  tug:        "TUG/DREDGE",
  other:      "OTHER",
};
function getVesselColor(v: import("../hooks/useTracking").Vessel): string {
  if (v.vessel_category) return VESSEL_CAT_COLORS[v.vessel_category] ?? "#718096";
  // Fallback to ship_type code when category not yet classified
  const t = v.ship_type ?? 0;
  if (t >= 80 && t <= 89) return "#e53e3e";
  if (t >= 70 && t <= 79) return "#38a169";
  if (t >= 60 && t <= 69) return "#4299e1";
  if (t >= 40 && t <= 49) return "#ed8936";
  if (t === 35)            return "#ff4040";
  if (t >= 50 && t <= 59) return "#ed8936";
  if (t >= 30 && t <= 35) return "#00bcd4";
  return "#718096";
}

// ── Tactical marker ───────────────────────────────────────────────────────────
function mkTacMarker(ev: ConflictEvent, isNew: boolean): L.DivIcon {
  const col = EVENT_COLORS[ev.event_type] ?? "#888888";
  const sev = ev.severity ?? 1;
  let coreSize: number, rings: number, speed: number;
  if (sev >= 9)      { coreSize = 20; rings = 3; speed = 1.1; }
  else if (sev >= 7) { coreSize = 16; rings = 3; speed = 1.6; }
  else if (sev >= 4) { coreSize = 12; rings = 2; speed = 2.4; }
  else               { coreSize = 8;  rings = 1; speed = 3.5; }
  const halfCore = coreSize / 2;
  // Invisible hit area — minimum 44px so the marker is always easy to click
  const hitSize  = Math.max(44, coreSize + 20);
  const hitOff   = (hitSize - coreSize) / 2;

  let coreHtml: string;
  if (ev.event_type === "military") {
    // SVG 8-pointed explosion starburst — tactical strike marker
    coreHtml = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="-12 -12 24 24"
        style="position:absolute;inset:0;width:100%;height:100%;overflow:visible;
          filter:drop-shadow(0 0 5px ${col}) drop-shadow(0 0 10px ${col}99)">
        <polygon
          points="0,-10 1.5,-3.7 7.1,-7.1 3.7,-1.5 10,0 3.7,1.5 7.1,7.1 1.5,3.7 0,10 -1.5,3.7 -7.1,7.1 -3.7,1.5 -10,0 -3.7,-1.5 -7.1,-7.1 -1.5,-3.7"
          fill="${col}" opacity="0.95"/>
        <circle cx="0" cy="0" r="2.8" fill="#fff" opacity="0.9"/>
        <circle cx="0" cy="0" r="1.2" fill="${col}" opacity="0.7"/>
      </svg>
    `;
  } else if (ev.event_type === "cyber") {
    coreHtml = `<div style="position:absolute;inset:0;background:${col};opacity:.85;
      clip-path:polygon(50% 0%,93% 25%,93% 75%,50% 100%,7% 75%,7% 25%);
      box-shadow:0 0 8px ${col};"></div>`;
  } else if (ev.event_type === "diplomatic") {
    coreHtml = `<div style="position:absolute;inset:1px;background:${col};border-radius:3px;opacity:.85;
      box-shadow:0 0 8px ${col};"></div>`;
  } else {
    coreHtml = `<div style="position:absolute;inset:1px;background:${col};border-radius:50%;opacity:.85;
      box-shadow:0 0 8px ${col};"></div>`;
  }

  const critHtml = sev >= 9
    ? `<div class="tac-crit" style="position:absolute;inset:0;border-radius:50%;background:${col};opacity:.35;"></div>`
    : "";

  const wrapperClass = isNew ? "tac-new" : "";

  return safeDivIcon({
    className: "",
    html: `
      <div style="position:relative;width:${hitSize}px;height:${hitSize}px;pointer-events:auto;cursor:pointer;">
        <div class="${wrapperClass}" style="position:absolute;top:${hitOff}px;left:${hitOff}px;width:${coreSize}px;height:${coreSize}px;">
          ${critHtml}${coreHtml}
        </div>
      </div>`,
    iconSize:   [hitSize, hitSize],
    iconAnchor: [hitSize / 2, hitSize / 2],
    popupAnchor:[0, -halfCore - 4],
  });
}

// ── Intelligence popup ────────────────────────────────────────────────────────
function mkPopupHtml(ev: ConflictEvent): string {
  const col       = EVENT_COLORS[ev.event_type] ?? "#888888";
  const rl        = relLabel(ev.source_reliability);
  const rc        = relColor(ev.source_reliability);
  const sc        = sevColor(ev.severity);
  const isParked  = ev.lat != null && Math.abs(ev.lat - (-25)) < 0.5;
  const ts        = new Date(ev.timestamp).toLocaleString("en-US", {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
    timeZoneName: "short",
  });
  const locLine = ev.location_name && ev.location_name.toLowerCase() !== "unknown"
    ? `<div style="grid-column:1/-1;color:#7888a0">📍 ${escapeHtml(ev.location_name)}${isParked ? " <span style='color:#f0883e'>[UNRESOLVED]</span>" : ""}</div>`
    : isParked ? `<div style="grid-column:1/-1;color:#f0883e">⚠ LOCATION UNRESOLVED</div>` : "";

  const coordLabel = `<div style="grid-column:1/-1;color:#a7b9cd;font-size:11px;">LOCATION: ${escapeHtml(ev.geolocation_precision || "unknown").toUpperCase()} · uncertainty not calibrated</div>`;
  // Multiple source records; transmission lineage and independence remain unassessed
  const crossConfirmed = hasMultipleReports(ev);
  const viralAmp = !crossConfirmed && isViralAmplification(ev);
  const nets = getNetworks(ev);
  const netsLabel = nets.map((n: string) => NETWORK_META[n]?.short ?? n).join(" + ");
  const multiSrc = (ev.report_count ?? 0) > 1
    ? crossConfirmed
      ? `<div style="grid-column:1/-1;color:#3fb950;font-weight:700">
          ↗ MULTIPLE REPORTS · ${netsLabel} (${ev.report_count} reports)
         </div>`
      : viralAmp
        ? `<div style="grid-column:1/-1;color:#d29922">
            ⚡ AMPLIFIED — ${ev.report_count} reports, single network (${netsLabel})
           </div>`
        : `<div style="grid-column:1/-1;color:#58a6ff">
            🔗 ${ev.report_count} reports · ${netsLabel || "unclassified"}
           </div>`
    : "";
  const srcLink = ev.source_url
    ? `<a href="${escapeHtml(safeUrl(ev.source_url))}" target="_blank" rel="noopener noreferrer"
         style="display:block;margin-top:8px;color:#58a6ff;font-size:11px;text-decoration:none;opacity:.8"
         onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.8">↗ OPEN SOURCE</a>` : "";

  // New enriched fields
  const evAny = ev as any;
  const subtypeKey = evAny.military_subtype
    ? evAny.military_subtype as MilSubtype
    : (ev.event_type === "military" ? getMilSubtype(ev.summary || "") : null);
  const subtypeLine = subtypeKey && subtypeKey !== "default" && ev.event_type === "military"
    ? `<div style="grid-column:1/-1;color:${col};font-weight:700;font-size:11px;letter-spacing:1px;">
        ⚡ ${MIL_SUBTYPE_LABELS[subtypeKey as MilSubtype]?.toUpperCase() ?? subtypeKey.toUpperCase()}
       </div>` : "";
  const actorLine = evAny.actor
    ? `<div style="grid-column:1/-1;color:#c8d6e5">👤 ${escapeHtml(evAny.actor)}</div>` : "";
  const casualtyLine = evAny.casualties
    ? `<div style="grid-column:1/-1;color:#f85149;font-weight:600">🩸 ${escapeHtml(evAny.casualties)}</div>` : "";
  const friendlySource = SOURCE_NAMES[ev.source] ?? SOURCE_NAMES[ev.channel_name] ?? ev.channel_name ?? ev.source ?? "—";

  // Thermal association metadata; proximity is not causation
  const hasSatelliteConfirm = (ev.confirmed_networks || "").includes("SATELLITE");
  const satBadge = hasSatelliteConfirm
    ? `<div style="grid-column:1/-1;display:flex;align-items:center;gap:5px;
        background:#0d1f0d;border:1px solid #3fb95044;border-radius:3px;padding:3px 6px;margin-top:2px;">
        <span style="color:#3fb950;font-size:11px">🛰 NASA VIIRS THERMAL ASSOCIATION</span>
        <span style="font-size:11px;color:#2a8a40">Nearby thermal observation; cause, timing and association require review</span>
       </div>` : "";

  // Satellite imagery section — lazy-loaded on popupopen for sev≥5 events with coordinates
  const hasCoords = ev.lat != null && ev.lon != null;
  const highSev = (ev.severity ?? 0) >= 5;
  const imagerySection = hasCoords && highSev ? `
    <div style="margin-top:10px;border-top:1px solid rgba(88,166,255,.08);padding-top:8px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
        <span style="font-size:11px;color:#8fb7d1;letter-spacing:0.5px">MAXAR/ESRI · SAT IMAGERY · ArcGIS</span>
        <span style="font-size:11px;color:#83a0b7">capture date varies</span>
      </div>
      <img data-ev-img="${ev.id}"
        style="width:100%;height:220px;object-fit:cover;display:none;border:1px solid #1e3a5a;border-radius:3px;background:#050d15;"
        onerror="this.style.display='none';document.querySelector('[data-ev-err=\\'${ev.id}\\']').style.display='flex'" />
      <div data-ev-load="${ev.id}"
        style="height:60px;display:flex;align-items:center;justify-content:center;gap:6px;
          color:#8da3b7;font-size:11px;border:1px solid #1e3a5a;border-radius:3px;background:#050d15;">
        <span style="font-size:14px">🛰</span><span>Loading satellite imagery…</span>
      </div>
      <div data-ev-err="${ev.id}"
        style="display:none;height:60px;align-items:center;justify-content:center;flex-direction:column;
          gap:4px;color:#8da3b7;font-size:11px;border:1px solid #1a2a3a;border-radius:3px;background:#050d15;">
        <span style="font-size:14px">🌥</span><span>No clear pass in last 30 days</span>
      </div>
      <div data-ev-links="${ev.id}" style="display:none;margin-top:5px;display:flex;gap:5px;flex-wrap:wrap"></div>
    </div>` : "";

  return `
    <div style="font-family:'Courier New',Courier,monospace;font-size:11px;color:#b0bec5;
      min-width:300px;max-width:390px;padding:12px 14px;line-height:1.5;">
      <div style="font-size:11px;letter-spacing:2.5px;font-weight:700;
        display:flex;justify-content:space-between;align-items:center;
        margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(88,166,255,.15);">
        <span style="color:${col}">${(ev.event_type ?? "UNKNOWN").toUpperCase()} INTELLIGENCE</span>
        <span style="color:${rc};padding:1px 5px;border:1px solid ${rc}44;border-radius:2px;background:${rc}14;">${rl}</span>
      </div>
      <div style="font-size:12px;color:#e8d8a0;font-weight:600;line-height:1.55;
        margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,.06);
        font-family:system-ui,-apple-system,sans-serif;">
        ${ev.summary || ev.raw_text?.slice(0, 200) || "—"}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px 12px;font-size:11px;color:#5a6a7a;">
        <div>SEVERITY <span style="color:${sc};font-weight:700">${severityLabel(ev)}</span></div>
        <div>🕐 ${ts}</div>
        ${subtypeLine}
        ${actorLine}
        ${casualtyLine}
        <div style="grid-column:1/-1;color:#7888a0">📡 ${escapeHtml(friendlySource)}</div>
        ${locLine}
        ${coordLabel}
        ${multiSrc}
        ${satBadge}
      </div>
      ${srcLink}
      ${imagerySection}
    </div>`;
}

// ── Haversine distance (km) ───────────────────────────────────────────────────
function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 +
            Math.cos(lat1 * Math.PI/180) * Math.cos(lat2 * Math.PI/180) * Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

// ── Event cluster ─────────────────────────────────────────────────────────────
interface EventCluster {
  events: ConflictEvent[];
  lat: number;
  lon: number;
  representative: ConflictEvent;   // highest-severity event
  confirmedCount: number;          // events with report_count >= 2
  disputedCount: number;           // events with conflicting sources
}

// Group events within CLUSTER_KM of each other (greedy, highest-sev first)
const CLUSTER_KM = 3;

function clusterEvents(events: ConflictEvent[]): EventCluster[] {
  // Sort descending by severity so the most important event is the cluster centre
  const sorted = [...events].sort((a, b) => (b.severity ?? 0) - (a.severity ?? 0));
  const used = new Set<number>();
  const clusters: EventCluster[] = [];

  for (let i = 0; i < sorted.length; i++) {
    if (used.has(i)) continue;
    const anchor = sorted[i];
    if (anchor.lat == null || anchor.lon == null) continue;

    const group: ConflictEvent[] = [anchor];
    used.add(i);

    for (let j = i + 1; j < sorted.length; j++) {
      if (used.has(j)) continue;
      const other = sorted[j];
      if (other.lat == null || other.lon == null) continue;
      if (haversineKm(anchor.lat!, anchor.lon!, other.lat!, other.lon!) <= CLUSTER_KM) {
        group.push(other);
        used.add(j);
      }
    }

    // Centroid
    const lat = group.reduce((s, e) => s + e.lat!, 0) / group.length;
    const lon = group.reduce((s, e) => s + e.lon!, 0) / group.length;

    // Cross-verification stats
    const confirmedCount = group.filter(hasMultipleReports).length;

    // DISPUTED: events in same cluster with very different severity (>3 apart) suggest conflicting reports
    let disputedCount = 0;
    if (group.length > 1) {
      const maxSev = Math.max(...group.map((e) => e.severity ?? 5));
      const minSev = Math.min(...group.map((e) => e.severity ?? 5));
      /* Different severity scores are not evidence of a contradictory claim. */
    }

    clusters.push({ events: group, lat, lon, representative: anchor, confirmedCount, disputedCount });
  }

  return clusters;
}

// ── Cluster marker icon ───────────────────────────────────────────────────────
function mkClusterMarker(cluster: EventCluster, isNew: boolean): L.DivIcon {
  const rep = cluster.representative;
  const count = cluster.events.length;
  const col = EVENT_COLORS[rep.event_type] ?? "#888888";
  const sev = rep.severity ?? 1;
  const isConfirmed = cluster.confirmedCount > 0;
  const isDisputed  = cluster.disputedCount > 0;
  // SATELLITE confirmation: NASA FIRMS thermal match — highest-confidence independent source
  const isSatConfirmed = cluster.events.some((e) => (e.confirmed_networks || "").includes("SATELLITE"));

  let coreSize: number;
  if (sev >= 9)      { coreSize = 22; }
  else if (sev >= 7) { coreSize = 18; }
  else if (sev >= 4) { coreSize = 14; }
  else               { coreSize = 10; }
  const halfCore = coreSize / 2;
  // Invisible hit area — minimum 44px so the marker is always easy to click
  const hitSize  = Math.max(44, coreSize + 20);
  const hitOff   = (hitSize - coreSize) / 2;

  // Core shape matches event type + military subtype overlay
  let coreHtml: string;
  if (rep.event_type === "military") {
    // Detect subtype from summary — prefer classifier field if present, else parse text
    const subtype = getMilSubtype((rep as any).military_subtype || rep.summary || "");
    const overlay = milSubtypeOverlay(subtype);
    coreHtml = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="-12 -12 24 24"
        style="position:absolute;inset:0;width:100%;height:100%;overflow:visible;
          filter:drop-shadow(0 0 5px ${col}) drop-shadow(0 0 10px ${col}99)">
        <polygon
          points="0,-10 1.5,-3.7 7.1,-7.1 3.7,-1.5 10,0 3.7,1.5 7.1,7.1 1.5,3.7 0,10 -1.5,3.7 -7.1,7.1 -3.7,1.5 -10,0 -3.7,-1.5 -7.1,-7.1 -1.5,-3.7"
          fill="${col}" opacity="0.95"/>
        ${overlay}
        <circle cx="0" cy="0" r="2" fill="#fff" opacity="${overlay ? 0.0 : 0.9}"/>
      </svg>`;
  } else if (rep.event_type === "thermal_anomaly") {
    // Thermal anomaly: concentric circle glow — visually distinct from military starbursts
    // Matches the orange FIRMS palette so it reads as "same signal, promoted to event"
    coreHtml = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="-12 -12 24 24"
        style="position:absolute;inset:0;width:100%;height:100%;overflow:visible;
          filter:drop-shadow(0 0 6px #ff8800) drop-shadow(0 0 12px #ff440055)">
        <circle cx="0" cy="0" r="9" fill="#ff8800" opacity="0.85"/>
        <circle cx="0" cy="0" r="5" fill="#ffcc44" opacity="0.9"/>
        <circle cx="0" cy="0" r="2.5" fill="#fff" opacity="0.95"/>
      </svg>`;
  } else {
    coreHtml = `<div style="position:absolute;inset:1px;background:${col};border-radius:50%;opacity:.85;
      box-shadow:0 0 8px ${col};"></div>`;
  }

  // Evidence tags — reported disagreement, sensor metadata, multiple reports
  const veriBadge = isDisputed
    ? `<div style="position:absolute;top:-6px;right:-8px;
        background:#d29922;color:#000;font-size:11px;font-weight:900;
        padding:1px 4px;border-radius:2px;font-family:monospace;letter-spacing:0.5px;
        z-index:10;border:1px solid rgba(0,0,0,0.5);white-space:nowrap;">⚠ DISPUTED</div>`
    : isSatConfirmed
    ? `<div style="position:absolute;top:-6px;right:-8px;
        background:#0d6efd;color:#fff;font-size:11px;font-weight:900;
        padding:1px 4px;border-radius:2px;font-family:monospace;letter-spacing:0.5px;
        z-index:10;border:1px solid rgba(255,255,255,0.3);white-space:nowrap;">🛰 SAT</div>`
    : isConfirmed
    ? `<div style="position:absolute;top:-6px;right:-8px;
        background:#3fb950;color:#000;font-size:11px;font-weight:900;
        padding:1px 4px;border-radius:2px;font-family:monospace;letter-spacing:0.5px;
        z-index:10;border:1px solid rgba(0,0,0,0.5);white-space:nowrap;">↗ MULTIPLE REPORTS</div>`
    : "";

  // Count badge (only for clusters with > 1 event)
  const countBadge = count > 1
    ? `<div style="position:absolute;bottom:-7px;left:50%;transform:translateX(-50%);
        background:#1a2332;color:${col};font-size:11px;font-weight:900;
        padding:1px 5px;border-radius:10px;font-family:monospace;
        border:1px solid ${col}88;white-space:nowrap;z-index:10;">${count}×</div>`
    : "";

  const newGlow = isNew
    ? `box-shadow:0 0 0 2px rgba(88,166,255,0.5),0 0 0 4px rgba(88,166,255,0.12);` : "";
  // Sensor metadata ring
  const satRing = isSatConfirmed
    ? `<svg style="position:absolute;top:${hitOff - 5}px;left:${hitOff - 5}px;width:${coreSize + 10}px;height:${coreSize + 10}px;overflow:visible;pointer-events:none;z-index:5"
         viewBox="0 0 ${coreSize + 10} ${coreSize + 10}">
         <circle cx="${(coreSize + 10) / 2}" cy="${(coreSize + 10) / 2}" r="${(coreSize + 8) / 2}"
           fill="none" stroke="#0d6efd" stroke-width="1.5" stroke-dasharray="3 2" opacity="0.9"/>
       </svg>` : "";

  // New event pulse animation ring
  const pulseRing = isNew
    ? `<div style="position:absolute;top:${hitOff - 4}px;left:${hitOff - 4}px;
        width:${coreSize + 8}px;height:${coreSize + 8}px;border-radius:50%;
        border:2px solid #58a6ff;animation:conflictPulse 2s ease-out infinite;pointer-events:none;"></div>`
    : "";

  return safeDivIcon({
    className: "",
    html: `
      <div style="position:relative;width:${hitSize}px;height:${hitSize}px;pointer-events:auto;cursor:pointer;">
        ${satRing}
        ${pulseRing}
        <div style="position:absolute;top:${hitOff}px;left:${hitOff}px;width:${coreSize}px;height:${coreSize}px;${newGlow}">
          ${coreHtml}
          ${veriBadge}
          ${countBadge}
        </div>
      </div>`,
    iconSize:    [hitSize, hitSize],
    iconAnchor:  [hitSize / 2, hitSize / 2],
    popupAnchor: [0, -halfCore - 8],
  });
}

// ── Cluster popup HTML ────────────────────────────────────────────────────────
function mkClusterPopupHtml(cluster: EventCluster): string {
  const rep = cluster.representative;
  if (cluster.events.length === 1) return mkPopupHtml(rep);

  const col = EVENT_COLORS[rep.event_type] ?? "#888888";
  const isConfirmed = cluster.confirmedCount > 0;
  const isDisputed  = cluster.disputedCount > 0;
  const veriLabel = isDisputed ? "⚠ CONFLICTING REPORTS" : isConfirmed ? "↗ MULTIPLE REPORTS" : `${cluster.events.length} EVENTS · SAME LOCATION`;
  const veriColor = isDisputed ? "#d29922" : isConfirmed ? "#3fb950" : "#58a6ff";

  const rows = cluster.events
    .sort((a, b) => (b.severity ?? 0) - (a.severity ?? 0))
    .map((ev) => {
      const ts = new Date(ev.timestamp).toLocaleString("en-US", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      });
      const sc = sevColor(ev.severity ?? 1);
      const srcType = (ev.source || "").startsWith("rss_") ? "📰" : "📡";
      const rc = relColor(ev.source_reliability);
      const rl = relLabel(ev.source_reliability);
      const multiSrc = (() => {
        if ((ev.report_count ?? 1) <= 1) return "";
        if (hasMultipleReports(ev)) return `<span style="color:#3fb950;font-size:11px;margin-left:4px;">↗ MULTIPLE REPORTS ${ev.report_count}×</span>`;
        if (isViralAmplification(ev)) return `<span style="color:#d29922;font-size:11px;margin-left:4px;">⚡ AMPLIFIED ${ev.report_count}×</span>`;
        return `<span style="color:#58a6ff;font-size:11px;margin-left:4px;">🔗 ${ev.report_count}×</span>`;
      })();
      return `
        <div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:4px;">
            <span style="font-size:11px;color:#e8d8a0;font-family:system-ui,sans-serif;line-height:1.4;flex:1;">
              ${escapeHtml(ev.summary || ev.raw_text?.slice(0, 120) || "—")}
            </span>
            <span style="flex-shrink:0;font-size:11px;color:${sc};font-weight:700;font-family:monospace;">
              ${severityLabel(ev)}
            </span>
          </div>
          <div style="display:flex;gap:8px;font-size:11px;color:#96a8b8;font-family:monospace;flex-wrap:wrap;">
            <span>${srcType} ${escapeHtml(ev.channel_name || ev.source || "—")}</span>
            <span style="color:${rc}">${rl}</span>
            <span>🕐 ${ts}</span>
            ${multiSrc}
            ${ev.source_url ? `<a href="${escapeHtml(safeUrl(ev.source_url))}" target="_blank" rel="noopener noreferrer"
              style="color:#58a6ff;text-decoration:none;opacity:.7"
              onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.7">↗ SOURCE</a>` : ""}
          </div>
        </div>`;
    }).join("");

  return `
    <div style="font-family:'Courier New',Courier,monospace;font-size:11px;color:#b0bec5;
      min-width:290px;max-width:380px;padding:12px 14px;line-height:1.5;">
      <div style="font-size:11px;letter-spacing:2px;font-weight:700;
        display:flex;justify-content:space-between;align-items:center;
        margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(88,166,255,.15);">
        <span style="color:${col}">📍 ${escapeHtml(rep.location_name?.toUpperCase() || "LOCATION CLUSTER")}</span>
        <span style="color:${veriColor};padding:1px 5px;border:1px solid ${veriColor}44;
          border-radius:2px;background:${veriColor}14;">${veriLabel}</span>
      </div>
      ${rows}
    </div>`;
}

// ── Static infrastructure data ────────────────────────────────────────────────
const CHOKEPOINTS = [
  { name: "Strait of Hormuz", lat: 26.60, lng: 56.50, critical: true  },
  { name: "Bab el-Mandeb",    lat: 12.60, lng: 43.40, critical: true  },
  { name: "Suez Canal",       lat: 30.45, lng: 32.35, critical: true  },
  { name: "Turkish Straits",  lat: 41.12, lng: 29.08, critical: false },
];

const BASES = [
  { name: "Al Udeid AB (USAF/Qatar)",    lat: 25.12, lng: 51.32, col: "#58a6ff" },
  { name: "Al Dhafra AB (USAF/UAE)",     lat: 24.25, lng: 54.55, col: "#58a6ff" },
  { name: "Camp Lemonnier (USAF/DJ)",    lat: 11.55, lng: 43.16, col: "#58a6ff" },
  { name: "Ali Al Salem AB (USAF/KW)",   lat: 29.34, lng: 47.52, col: "#58a6ff" },
  { name: "Diego Garcia (USAF)",         lat: -7.31, lng: 72.41, col: "#58a6ff" },
  { name: "Incirlik AB (NATO/TR)",       lat: 37.00, lng: 35.43, col: "#9b59b6" },
  { name: "Muwaffaq Salti AB (JO)",      lat: 32.36, lng: 36.26, col: "#9b59b6" },
  { name: "Nevatim AB (IDF)",            lat: 31.21, lng: 35.01, col: "#3fb950" },
  { name: "Palmachim AB (IDF)",          lat: 31.90, lng: 34.69, col: "#3fb950" },
  { name: "Fordow Enrichment (Iran)",    lat: 34.8834, lng: 50.2278, col: "#f85149" },
  { name: "Natanz Enrichment (Iran)",    lat: 33.72, lng: 51.73, col: "#f85149" },
  { name: "Bushehr Nuclear (Iran)",      lat: 28.83, lng: 50.89, col: "#f85149" },
  { name: "Isfahan Military (Iran)",     lat: 32.65, lng: 51.67, col: "#d43030" },
  { name: "Khmeimim AB (Russia/Syria)",  lat: 35.40, lng: 35.95, col: "#d29922" },
  { name: "Al Minhad AB (UAE)",          lat: 25.03, lng: 55.37, col: "#9b59b6" },
  { name: "Prince Sultan AB (SA)",       lat: 24.06, lng: 47.58, col: "#58a6ff" },
  { name: "Mina Salman NB (Bahrain)",    lat: 26.20, lng: 50.60, col: "#58a6ff" },
];

// Key oil refineries
const REFINERIES = [
  { name: "Ras Tanura Refinery (SA)",     lat: 26.65, lng: 50.17 },
  { name: "Abadan Refinery (Iran)",       lat: 30.34, lng: 48.28 },
  { name: "Bandar Abbas Refinery (Iran)", lat: 27.22, lng: 56.25 },
  { name: "Tehran Refinery (Iran)",       lat: 35.63, lng: 51.33 },
  { name: "Haifa Refinery (Israel)",      lat: 32.82, lng: 35.04 },
  { name: "Jubail Refinery (SA)",         lat: 27.01, lng: 49.62 },
  { name: "Kuwait KNPC Mina Abdullah",    lat: 29.04, lng: 48.08 },
  { name: "Ruwais Refinery (UAE)",        lat: 24.11, lng: 52.73 },
  { name: "Erbil Refinery (Iraq)",        lat: 36.19, lng: 43.99 },
  { name: "Baiji Refinery (Iraq)",        lat: 34.94, lng: 43.49 },
];

// Key airfields (strategic/military — bases already listed separately)
const AIRFIELDS = [
  { name: "Mehrabad Airport (Iran-military)", lat: 35.69, lng: 51.31 },
  { name: "Shahid Nojeh AB (Iran)",           lat: 35.21, lng: 48.65 },
  { name: "Dezful AB (Iran)",                 lat: 32.43, lng: 48.40 },
  { name: "Tabriz AB (Iran)",                 lat: 38.13, lng: 46.24 },
  { name: "Mashhad AB (Iran)",                lat: 36.24, lng: 59.64 },
  { name: "King Khalid Mil City (SA)",        lat: 27.90, lng: 45.52 },
  { name: "Aleppo Airbase (Syria)",           lat: 36.18, lng: 37.22 },
  { name: "H4 Airbase (Jordan)",              lat: 33.19, lng: 38.20 },
  { name: "Tiyas AB T4 (Syria)",              lat: 34.52, lng: 37.62 },
  { name: "Deir ez-Zor Airport (Syria)",      lat: 35.29, lng: 40.18 },
  { name: "Ramat David AB (Israel)",          lat: 32.67, lng: 35.18 },
  { name: "Ramon AB (Israel)",                lat: 29.73, lng: 34.95 },
];

// Key pipeline segments (simplified lat/lon waypoints)
const OIL_PIPELINES: { name: string; points: [number, number][] }[] = [
  {
    name: "Baku–Tbilisi–Ceyhan (BTC)",
    points: [[40.38,49.85],[41.70,45.35],[41.00,41.50],[36.80,36.10]],
  },
  {
    name: "Iraq–Turkey Pipeline (Kirkuk–Ceyhan)",
    points: [[35.47,44.39],[37.10,42.50],[37.55,37.00],[36.80,36.10]],
  },
  {
    name: "Saudi East–West Pipeline (Petroline)",
    points: [[26.31,49.98],[24.68,46.72],[23.50,43.00],[23.00,38.50]],
  },
  {
    name: "IGAT Gas Pipeline (Iran)",
    points: [[27.18,56.27],[30.15,50.50],[33.00,48.50],[35.50,46.00]],
  },
  {
    name: "Arab Gas Pipeline",
    points: [[30.00,32.30],[30.09,32.42],[31.20,34.79],[32.20,34.98]],
  },
];

const GAS_PIPELINES: { name: string; points: [number, number][] }[] = [
  {
    name: "South Pars/North Dome Gas Field Pipeline",
    points: [[27.50,51.00],[27.00,50.50],[26.65,50.17]],
  },
  {
    name: "Iran–Turkey Gas Pipeline",
    points: [[38.08,46.30],[38.50,44.00],[39.90,41.10],[39.92,40.75]],
  },
  {
    name: "Dolphin Gas Pipeline (Qatar–UAE–Oman)",
    points: [[25.58,51.53],[24.50,53.50],[23.59,58.59]],
  },
];

// ── Layer / filter state types ────────────────────────────────────────────────
type LayerState = {
  bases:        boolean;
  chokepoints:  boolean;
  refineries:   boolean;
  airfields:    boolean;
  oilPipelines: boolean;
  gasPipelines: boolean;
  aircraft:     boolean;
  vessels:      boolean;
  jamming:      boolean;
};

// ── Prop interface ────────────────────────────────────────────────────────────
interface MapPanelProps {
  events:        ConflictEvent[];
  aircraft:      Aircraft[];
  vessels:       Vessel[];
  tleData:       TLERecord[];
  jammingZones:  JammingZone[];
  focusEventId?: number | null;   // Set by parent to fly-to + open a specific event
  // Intel Pulse overlay props
  allEvents?:    ConflictEvent[];
  onIntelEventClick?: (evt: ConflictEvent) => void;
  // NASA FIRMS thermal hotspots
  firmsHotspots?: Array<{
    lat: number; lon: number; frp: number; conf: number | null; confidence_label?: string; synthetic?: boolean; ts: string;
    google_maps_url: string; copernicus_url: string;
    wms_thumbnail: string;
    gibs_viirs_thumb: string; gibs_modis_thumb: string; gibs_landsat_thumb: string;
    eo_browser_url: string; landsatlook_url: string; planet_url: string;
    probable_flare: boolean; flare_zone: string;
    matched: boolean;
  }>;
}


// ── SITREP Mini Video Player ────────────────────────────────────────────────────
const SITREP_COLORS: Record<string, string> = {
  STABLE: "#3fb950", ELEVATED: "#d29922", ESCALATING: "#f0883e", CRITICAL: "#f85149",
};


export function MapPanel({ events, aircraft, vessels, tleData: _tleData, jammingZones, focusEventId = null, allEvents, onIntelEventClick, firmsHotspots = [] }: MapPanelProps) {
  const divRef   = useRef<HTMLDivElement>(null);
  const mapRef   = useRef<L.Map | null>(null);
  const evLayRef  = useRef<L.LayerGroup | null>(null);
  const acLayRef  = useRef<L.LayerGroup | null>(null);
  const vsLayRef  = useRef<L.LayerGroup | null>(null);
  const jzLayRef  = useRef<L.LayerGroup | null>(null);
  const refLayRef = useRef<L.LayerGroup | null>(null);
  const afdLayRef = useRef<L.LayerGroup | null>(null);
  const oilLayRef = useRef<L.LayerGroup | null>(null);
  const gasLayRef = useRef<L.LayerGroup | null>(null);
  const basLayRef = useRef<L.LayerGroup | null>(null);
  const chkLayRef = useRef<L.LayerGroup | null>(null);
  const firmsLayRef = useRef<L.LayerGroup | null>(null);  // NASA FIRMS thermal hotspots

  const acTrackLayRef = useRef<L.LayerGroup | null>(null);

  const [selected,     setSelected]     = useState<ConflictEvent | null>(null);
  const [filterOpen,   setFilterOpen]   = useState(false);
  const prevIdsRef     = useRef<Set<number>>(new Set());
  const newEventIdsRef = useRef<Set<number>>(new Set());
  // Track which cluster's popup is open so we can reopen it after a marker rebuild
  const openRepIdRef   = useRef<number | null>(null);
  // Map repId → marker so focusEventId can find and open the right popup
  const markersByRepId = useRef<Map<number, L.Marker>>(new Map());

  // Active event type filters
  const [activeTypes, setActiveTypes] = useState<Set<string>>(
    new Set(Object.keys(EVENT_TYPE_CONFIG))
  );

  // Layer visibility
  const [layers, setLayers] = useState<LayerState>({
    bases:        true,
    chokepoints:  true,
    refineries:   true,
    airfields:    true,
    oilPipelines: true,
    gasPipelines: true,
    aircraft:     true,
    vessels:      true,
    jamming:      true,
  });

  // ── ADS-B enhanced layer — direct adsb.lol V2 feed ──────────────────────
  const [adsbFilters, setAdsbFilters] = useState<AircraftFilters>({});
  const [adsbSelected, setAdsbSelected] = useState<ADSBAircraft | null>(null);

  // Bounded backend receiver coverage is documented by the provider status API.
  // Backend controls provider activation; no separate browser feed bypasses that policy.
  const adsbAircraft: ADSBAircraft[] = useMemo(() => aircraft.map(a => ({
    hex:a.icao24,flight:a.callsign,r:a.registration,t:a.type,lat:a.lat,lon:a.lon,
    alt_baro:a.on_ground ? "ground" as const : (a.altitude == null ? undefined : a.altitude / .3048),
    gs:a.velocity == null ? undefined : a.velocity * 1.943844, track:a.heading ?? undefined,
    squawk:a.squawk, emergency:a.emergency, category:a.category, seen:a.age_seconds??undefined,seen_pos:a.age_seconds??undefined,
  })),[aircraft]);

  const adsbFiltered = useMemo(
    () => applyADSBFilters(adsbAircraft, adsbFilters),
    [adsbAircraft, adsbFilters],
  );

  const trackHistory = useTrackHistory(adsbFiltered);

  const geoEvents = useMemo(
    () => events.filter(
      (e) =>
        e.lat != null && e.lon != null &&
        // Exclude sentinel "unknown location" marker placed in the Indian Ocean
        !(Math.abs(e.lat - (-25)) < 1 && Math.abs(e.lon - 80) < 1) &&
        activeTypes.has(e.event_type ?? "unclassified")
    ),
    [events, activeTypes],
  );

  // Track newly arrived events (via ref — avoids triggering extra marker rebuilds)
  useEffect(() => {
    const current = new Set(geoEvents.map((e) => e.id));
    const fresh = new Set<number>();
    for (const id of current) if (!prevIdsRef.current.has(id)) fresh.add(id);
    newEventIdsRef.current = fresh;
    prevIdsRef.current = current;
    if (fresh.size > 0) {
      const t = setTimeout(() => { newEventIdsRef.current = new Set(); }, 3000);
      return () => clearTimeout(t);
    }
  }, [geoEvents]);

  // Inject tactical CSS once
  useEffect(() => {
    if (document.getElementById("tactical-map-css")) return;
    const style = document.createElement("style");
    style.id = "tactical-map-css";
    style.textContent = TACTICAL_CSS;
    document.head.appendChild(style);
  }, []);

  // ── Init Leaflet map ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!divRef.current || mapRef.current) return;

    const map = L.map(divRef.current, {
      center: [30, 45], zoom: 6,
      zoomControl: false, attributionControl: true, preferCanvas: true, renderer:new OwnedFrameCanvas(),
      closePopupOnClick: false,   // keep popup open when clicking map or SOURCE links
      fadeAnimation: true,
      zoomAnimation: true,
      markerZoomAnimation: true,
    });

    if (SHOWCASE) {
      map.setView([29, 44], 5);
      for (const file of ["coastlines", "countries"]) {
        apiFetch(`/textures/${file}.json`).then(r => r.json()).then(data => {
          if (mapRef.current !== map) return;
          L.geoJSON(data, {style:{color:file === "coastlines" ? "#527784" : "#294653",weight:1,opacity:.8},interactive:false}).addTo(map);
        }).catch(() => {});
      }
      map.attributionControl.addAttribution("Natural Earth · synthetic exercise overlay");
      for (const [label, lat, lon] of [["IRAN",32.4,54],["IRAQ",33,43.7],["SAUDI ARABIA",24,44],["OMAN",21.5,56],["EGYPT",27,30],["TURKEY",39,35]] as const) {
        L.marker([lat,lon],{interactive:false,icon:safeDivIcon({className:"exercise-map-label",html:label,iconSize:[110,20]})}).addTo(map);
      }
    } else {
    // ESRI World Imagery — satellite base (real terrain, deserts, mountains, rivers)
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: 'Tiles &copy; <a href="https://www.esri.com">Esri</a>, Maxar, Earthstar Geographics',
        maxZoom: 19,
        className: "tac-imagery-base",
        keepBuffer: 6,
        updateWhenZooming: false,
        updateWhenIdle: true,
      }
    ).addTo(map);

    // ESRI Hybrid Reference — country borders, city labels, coastlines on top
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "",
        maxZoom: 19,
        className: "tac-imagery-ref",
        pane: "shadowPane",
        keepBuffer: 6,
        updateWhenZooming: false,
        updateWhenIdle: true,
      }
    ).addTo(map);

    }

    L.control.zoom({ position: "bottomright" }).addTo(map);

    // ── Static layers (built once) ────────────────────────────────────────
    // Chokepoints
    const chkLay = L.layerGroup().addTo(map);
    CHOKEPOINTS.forEach((cp) => {
      const col = cp.critical ? "#d29922" : "#7a6030";
      L.circleMarker([cp.lat, cp.lng], {
        radius: cp.critical ? 18 : 12, color: col, fillColor: col,
        weight: 1, fillOpacity: 0.05, dashArray: "6 4",
      }).addTo(chkLay).bindTooltip(`⚓ ${cp.name}${cp.critical ? " · CRITICAL CHOKEPOINT" : ""}`, { direction: "top" });
      if (cp.critical) {
        L.circleMarker([cp.lat, cp.lng], {
          radius: 8, color: col, fillColor: col, weight: 1.5, fillOpacity: 0.15,
        }).addTo(chkLay);
      }
    });
    chkLayRef.current = chkLay;

    // Military bases — pentagon icon
    const basLay = L.layerGroup().addTo(map);
    BASES.forEach((b) => {
      L.marker([b.lat, b.lng], {
        icon: safeDivIcon({
          className: "",
          html: `<div style="width:14px;height:14px;background:${b.col};clip-path:polygon(50% 0%, 100% 38%, 82% 100%, 18% 100%, 0% 38%);
            box-shadow:0 0 6px ${b.col};opacity:0.9;"></div>`,
          iconSize: [14, 14], iconAnchor: [7, 7],
        }),
        zIndexOffset: 200,
      }).addTo(basLay).bindTooltip(`⬟ ${b.name}`, { direction: "top" });
    });
    basLayRef.current = basLay;

    // Refineries (initially hidden) — pulsing red diamond
    const refLay = L.layerGroup();
    REFINERIES.forEach((r) => {
      L.marker([r.lat, r.lng], {
        icon: safeDivIcon({
          className: "",
          html: `<div style="width:12px;height:12px;background:#ff4444;transform:rotate(45deg);
            box-shadow:0 0 8px #ff4444;opacity:0.9;animation:conflictPulse 3s ease-out infinite;"></div>`,
          iconSize: [12, 12], iconAnchor: [6, 6],
        }),
        zIndexOffset: 150,
      }).addTo(refLay).bindTooltip(`⛽ ${r.name}`, { direction: "top" });
    });
    refLayRef.current = refLay;

    // Airfields (initially hidden)
    const afdLay = L.layerGroup();
    AIRFIELDS.forEach((a) => {
      L.marker([a.lat, a.lng], {
        icon: safeDivIcon({
          className: "",
          html: `<div style="font-size:12px;line-height:1;text-shadow:0 0 6px #58a6ff88;
            opacity:.8;color:#7ab8d4;">✈</div>`,
          iconSize: [12, 12], iconAnchor: [6, 6],
        }),
        zIndexOffset: 120,
      }).addTo(afdLay).bindTooltip(`✈ ${a.name}`, { direction: "top" });
    });
    afdLayRef.current = afdLay;

    // Oil pipelines (initially hidden)
    const oilLay = L.layerGroup();
    OIL_PIPELINES.forEach((p) => {
      L.polyline(p.points as [number,number][], {
        color: "#d29922", weight: 2.5, opacity: 0.65, dashArray: "8 4",
      }).addTo(oilLay).bindTooltip(`🛢 ${p.name}`, { direction: "center", sticky: true });
    });
    oilLayRef.current = oilLay;

    // Gas pipelines (initially hidden)
    const gasLay = L.layerGroup();
    GAS_PIPELINES.forEach((p) => {
      L.polyline(p.points as [number,number][], {
        color: "#58a6ff", weight: 2, opacity: 0.55, dashArray: "10 5",
      }).addTo(gasLay).bindTooltip(`💧 ${p.name}`, { direction: "center", sticky: true });
    });
    gasLayRef.current = gasLay;

    // Dynamic layers
    evLayRef.current = L.layerGroup().addTo(map);
    acTrackLayRef.current = L.layerGroup().addTo(map);
    acLayRef.current = L.layerGroup().addTo(map);
    vsLayRef.current = L.layerGroup().addTo(map);
    jzLayRef.current = L.layerGroup().addTo(map);
    firmsLayRef.current = L.layerGroup().addTo(map);  // NASA FIRMS hotspots



    mapRef.current = map;
    return () => {
      map.stop(); map.closePopup();
      // Leaflet may otherwise destroy its Canvas renderer before remaining paths;
      // removing those paths then schedules a redraw against the destroyed canvas.
      const paths:L.Path[]=[];
      map.eachLayer(layer=>{if(layer instanceof L.Path)paths.push(layer);});
      paths.forEach(path=>map.removeLayer(path));
      mapRef.current=null;
      map.remove();
    };
  }, []);

  // ── NASA FIRMS satellite thermal hotspot layer ──────────────────────────────

  useEffect(() => {
    if (!firmsLayRef.current) return;
    firmsLayRef.current.clearLayers();

    firmsHotspots.forEach((h) => {
      // Skip non-flare hotspots that are already matched to a military event in the DB.
      // Those appear as SAT-confirmed military markers instead — no duplicate raw circle needed.
      if (!h.probable_flare && h.matched) return;

      const ts = new Date(h.ts).toUTCString().slice(0, 22);
      const isFlare = h.probable_flare;

      // FRP-based gradient for thermal hotspots
      let fillColor: string;
      let radius: number;
      let pulseRing: boolean = false;

      if (isFlare) {
        // Gas flares: yellow, smaller
        fillColor = "#cccc30";
        radius = 6;
      } else if (h.frp < 50) {
        // 0–50 MW: yellow
        fillColor = "#ffff00";
        radius = 8;
      } else if (h.frp < 150) {
        // 50–150 MW: orange
        fillColor = "#ff8800";
        radius = 11;
      } else if (h.frp < 300) {
        // 150–300 MW: deep orange
        fillColor = "#ff4400";
        radius = 14;
      } else {
        // 300+ MW: red with pulse
        fillColor = "#ff0000";
        radius = 17;
        pulseRing = true;
      }

      const confidenceLabel = h.confidence_label || (h.conf == null ? "unknown" : `numeric ${h.conf}`);
      const fillOpacity = confidenceLabel === "high" ? .85 : confidenceLabel === "low" ? .4 : .65;

      // Main circle with FRP-based color and confidence opacity
      const circle = L.circleMarker([h.lat, h.lon], {
        radius: radius,
        fillColor: fillColor,
        fillOpacity: fillOpacity,
        color: fillColor,
        weight: 1.5,
        opacity: fillOpacity,
      });

      // Add tooltip with FRP value
      const frpLabel = h.frp >= 100 ? `${Math.round(h.frp)}MW 🔥` : `${Math.round(h.frp)}MW`;
      circle.bindTooltip(frpLabel, { direction: "top", permanent: false });

      // Outer pulse ring for 300+ MW hotspots
      if (pulseRing) {
        L.circleMarker([h.lat, h.lon], {
          radius: radius + 4,
          fillColor: "none",
          fillOpacity: 0,
          color: "#ff0000",
          weight: 1,
          opacity: 0.3,
          dashArray: "2 2",
        }).addTo(firmsLayRef.current!);
      }

      // Inner dot for visual hierarchy
      L.circleMarker([h.lat, h.lon], {
        radius: Math.max(2, radius * 0.35),
        fillColor: "#ffffff",
        fillOpacity: isFlare ? 0.5 : 0.9,
        color: isFlare ? "#888800" : "#ffffff",
        weight: 0.5,
        opacity: isFlare ? 0.4 : fillOpacity,
      }).addTo(firmsLayRef.current!);

      // ── Sentinel-2 imagery block (only source that actually works) ──────────
      const hasSentinel = !!h.wms_thumbnail;

      // Large S2 image or "no imagery" fallback
      const s2ImageHtml = hasSentinel ? `
        <div style="margin:6px 0 0">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
            <span style="font-size:11px;color:#8fb7d1;letter-spacing:0.5px">SENTINEL-2 · 10m · ESA/COPERNICUS</span>
            <span style="font-size:11px;color:#83a0b7">30-day best scene</span>
          </div>
          <img src="${h.wms_thumbnail}"
            style="width:100%;height:260px;object-fit:cover;display:block;border:1px solid #1e3a5a;border-radius:3px;background:#050d15;"
            onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" />
          <div style="display:none;height:180px;align-items:center;justify-content:center;flex-direction:column;gap:6px;color:#8da3b7;font-size:11px;border:1px solid #1e3a5a;border-radius:3px;background:#050d15;">
            <span style="font-size:18px">🌥</span>
            <span>No clear pass in last 30 days</span>
            <span style="font-size:11px;color:#829aae">Cloud cover &gt;30% all passes</span>
          </div>
        </div>` : `
        <div style="height:100px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:4px;color:#8da3b7;font-size:11px;border:1px solid #1a2a3a;border-radius:3px;margin:6px 0 0;background:#050d15;">
          <span style="font-size:16px">🛰</span>
          <span>No Sentinel-2 imagery configured</span>
        </div>`;

      // Three viewer links — only working ones
      const linkStyle = "text-decoration:none;font-weight:700;font-size:11px;padding:3px 7px;border-radius:3px;border:1px solid";
      const viewerLinks = `
        <div style="margin-top:6px;display:flex;gap:5px;flex-wrap:wrap;align-items:center">
          <span style="font-size:11px;color:#8da3b7;font-family:monospace">OPEN IN:</span>
          <a href="${h.google_maps_url}" target="_blank" rel="noopener"
             style="${linkStyle} #1e4a2a;color:#3fb950;background:#0d1a10">🗺 GOOGLE MAPS</a>
          <a href="${h.copernicus_url}" target="_blank" rel="noopener"
             style="${linkStyle} #1e3a5a;color:#58a6ff;background:#0d1525">🛰 NASA WORLDVIEW</a>
          <a href="${h.eo_browser_url}" target="_blank" rel="noopener"
             style="${linkStyle} #3a2a1e;color:#d29922;background:#1a1205">🔬 COP BROWSER</a>
        </div>`;

      const flareTitle = isFlare ? "⛽ GAS FLARE / INDUSTRIAL" : "🛰 THERMAL ANOMALY";
      const flareTitleColor = isFlare ? "#aaaa20" : "#ff8800";
      const flareBanner = isFlare
        ? '<div style="font-size:11px;color:#888820;background:#1a1a00;padding:2px 5px;border-radius:2px;margin-bottom:4px;border-left:2px solid #666600">Industrial-region overlap; cause unassessed — ' + h.flare_zone + '</div>'
        : "";
      const popupHtml = `
        <div style="font-family:monospace;font-size:12px;min-width:320px;max-width:360px;color:#c9d1d9">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
            <div style="font-weight:700;color:${flareTitleColor};font-size:12px">${flareTitle}</div>
            <div style="font-size:11px;color:#8ea8be">${h.synthetic ? "SYNTHETIC SENSOR EXERCISE" : "NASA VIIRS-NOAA20"}</div>
          </div>
          ${flareBanner}
          <div style="display:flex;gap:12px;align-items:baseline;margin-bottom:2px">
            <span style="font-size:13px;font-weight:700;color:${isFlare ? "#cccc30" : (h.frp >= 80 ? "#ff6600" : "#ffcc00")}">${frpLabel}</span>
            <span style="font-size:11px;color:#6a8aaa">Detection confidence: ${escapeHtml(confidenceLabel)}</span>
            <span style="font-size:11px;color:#8ea8be">${h.lat.toFixed(4)}°N ${h.lon.toFixed(4)}°E</span>
          </div>
          <div style="font-size:11px;color:#8da3b7;margin-bottom:0">${ts} UTC</div>
          ${s2ImageHtml}
          ${viewerLinks}
        </div>`;

      circle.bindPopup(sanitizeHtml(popupHtml), { maxWidth: 380, autoPan: false });
      circle.addTo(firmsLayRef.current!);
    });
  }, [firmsHotspots]);

  // ── Layer visibility toggles ─────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const toggleLayer = (layRef: React.MutableRefObject<L.LayerGroup | null>, visible: boolean) => {
      if (!layRef.current) return;
      if (visible && !map.hasLayer(layRef.current)) layRef.current.addTo(map);
      else if (!visible && map.hasLayer(layRef.current)) layRef.current.remove();
    };
    toggleLayer(basLayRef,  layers.bases);
    toggleLayer(chkLayRef,  layers.chokepoints);
    toggleLayer(refLayRef,  layers.refineries);
    toggleLayer(afdLayRef,  layers.airfields);
    toggleLayer(oilLayRef,  layers.oilPipelines);
    toggleLayer(gasLayRef,  layers.gasPipelines);
  }, [layers]);

  // Memoize cluster computation — avoids re-clustering on every render
  const clusters = useMemo(() => clusterEvents(geoEvents), [geoEvents]);

  // ── Event markers (clustered) ─────────────────────────────────────────────
  useEffect(() => {
    if (!evLayRef.current) return;

    // ── Bug fix: save openRepIdRef BEFORE clearLayers() ───────────────────────
    // clearLayers() destroys open popups, firing popupclose on each marker.
    // The popupclose handler nulls openRepIdRef — so by the time we check it
    // below the ref would already be null. Capture it first.
    const savedOpenId = openRepIdRef.current;

    evLayRef.current.clearLayers();
    markersByRepId.current.clear();

    // Collect any marker that should be reopened after rebuild
    const toReopen: L.Marker[] = [];

    clusters.forEach((cluster) => {
      const rep    = cluster.representative;
      const isNew  = cluster.events.some((e) => newEventIdsRef.current.has(e.id));
      const isSel  = cluster.events.some((e) => e.id === selected?.id);

      const marker = L.marker([cluster.lat, cluster.lon], {
        icon: mkClusterMarker(cluster, isNew),
        zIndexOffset: isSel ? 1000 : (rep.severity ?? 0) * 10,
      });
      cluster.events.forEach(event=>markersByRepId.current.set(event.id,marker));
      // autoPan: false — prevents map from jumping/panning when popup opens
      marker.bindPopup(sanitizeHtml(mkClusterPopupHtml(cluster)), {
        maxWidth: 400,
        className: "",
        autoPan: false,
      });

      marker.on("click", (e: L.LeafletMouseEvent) => {
        // Stop both browser and Leaflet event propagation so the map's
        // closePopupOnClick handler never sees this click
        L.DomEvent.stop(e.originalEvent);
        openRepIdRef.current = rep.id;
        setSelected(rep);
        marker.openPopup();
      });

      // Lazy-load Sentinel-2 satellite imagery when popup opens (sev≥6 events with coords)
      marker.on("popupopen", () => {
        const sev = rep.severity ?? 0;
        if (sev < 6 || rep.lat == null || rep.lon == null) return;
        const imgEl  = document.querySelector(`img[data-ev-img="${rep.id}"]`) as HTMLImageElement | null;
        const loadEl = document.querySelector(`[data-ev-load="${rep.id}"]`) as HTMLElement | null;
        const errEl  = document.querySelector(`[data-ev-err="${rep.id}"]`) as HTMLElement | null;
        const lnkEl  = document.querySelector(`[data-ev-links="${rep.id}"]`) as HTMLElement | null;
        if (!imgEl || imgEl.getAttribute("data-loaded") === "true") return;
        imgEl.setAttribute("data-loaded", "true");
        apiFetch(`/api/events/${rep.id}/imagery`)
          .then((r) => (r.ok ? r.json() : Promise.reject()))
          .then((data: { s2_thumbnail: string; worldview_url: string; google_maps_url: string; copernicus_browser_url: string; unosat_url: string }) => {
            if (loadEl) loadEl.style.display = "none";
            if (data.s2_thumbnail) {
              imgEl.src = safeUrl(data.s2_thumbnail);
              imgEl.style.display = "block";
            } else {
              if (errEl) errEl.style.display = "flex";
            }
            // Inject viewer links
            if (lnkEl) {
              const ls = "text-decoration:none;font-weight:700;font-size:11px;padding:2px 6px;border-radius:3px;border:1px solid";
              lnkEl.style.display = "flex";
              lnkEl.innerHTML = sanitizeHtml(`
                <span style="font-size:11px;color:#8da3b7;font-family:monospace;align-self:center">OPEN IN:</span>
                <a href="${data.google_maps_url}" target="_blank" rel="noopener"
                   style="${ls} #1e4a2a;color:#3fb950;background:#0d1a10">🗺 MAPS</a>
                <a href="${data.worldview_url}" target="_blank" rel="noopener"
                   style="${ls} #1e3a5a;color:#58a6ff;background:#0d1525">🛰 WORLDVIEW</a>
                <a href="${data.copernicus_browser_url}" target="_blank" rel="noopener"
                   style="${ls} #3a2a1e;color:#d29922;background:#1a1205">🔬 COP BROWSER</a>
                <a href="${data.unosat_url}" target="_blank" rel="noopener"
                   style="${ls} #2a1a3a;color:#a78bfa;background:#1a0d2a">📊 UNOSAT</a>`);
            }
          })
          .catch(() => {
            if (loadEl) loadEl.style.display = "none";
            if (errEl) errEl.style.display = "flex";
          });
      });

      // When the popup is closed (X button or clicking the map), forget it
      marker.on("popupclose", () => {
        if (openRepIdRef.current === rep.id) openRepIdRef.current = null;
      });

      evLayRef.current!.addLayer(marker);
      if(savedOpenId!=null && cluster.events.some(event=>event.id===savedOpenId))toReopen.push(marker);

      // No accuracy ring: publisher ratings and sensor pixels are not calibrated location uncertainty.

    });

    // Reopen any popup that was open before the layer was rebuilt
    toReopen.forEach((m) => m.openPopup());
  }, [clusters]);

  // ── Live-feed click: fly to event and open its cluster popup ─────────────
  useEffect(() => {
    if (focusEventId === null || !mapRef.current) return;
    const marker = markersByRepId.current.get(focusEventId);
    if (!marker) return;
    const focused=events.find(event=>event.id===focusEventId);
    if(focused)setSelected(focused);
    const pos = marker.getLatLng();
    // Smoothly pan to event; don't zoom in too far — stay at current zoom if already close
    const currentZoom = mapRef.current.getZoom();
    mapRef.current.setView(pos, Math.max(currentZoom, 7), { animate: true, duration: 0.6 });
    // Brief delay lets the pan finish before opening the popup
    const focusTimer = setTimeout(() => {
      if (!mapRef.current || !mapRef.current.hasLayer(marker)) return;
      const repId = [...markersByRepId.current.entries()]
        .find(([, m]) => m === marker)?.[0] ?? null;
      if (repId !== null) {
        openRepIdRef.current = repId;
      }
      marker.openPopup();
    }, 700);
    return () => clearTimeout(focusTimer);
  }, [focusEventId]);

  // NOTE: flyTo removed — it was animating the map on every marker click,
  // which closed the popup mid-animation. Live-feed focus uses the new
  // focusEventId prop instead (see effect above).

  // ── Aircraft layer — altitude-colored SVG silhouettes via adsb.lol direct ──
  useEffect(() => {
    if (!acLayRef.current) return;
    acLayRef.current.clearLayers();
    if (!acTrackLayRef.current) return;
    acTrackLayRef.current.clearLayers();
    if (!layers.aircraft) return;

    // Render aircraft markers from direct adsb.lol feed
    adsbFiltered.forEach((ac) => {
      if (ac.lat == null || ac.lon == null) return;
      const cs = ac.flight?.trim() || ac.hex.toUpperCase();
      const altColor = getAltitudeColor(ac.alt_baro);
      const iconType = getIconType(ac);
      const isSel = adsbSelected?.hex === ac.hex;
      const isMil = (ac.dbFlags ?? 0) & 1;
      const isEmerg = ac.squawk === "7700" || ac.squawk === "7600" || ac.squawk === "7500";
      const flashCls = isEmerg ? "ac-emergency" : "";

      const iconUrl = createAircraftSvg(iconType, ac.track ?? 0, altColor, 32, isSel);

      const marker = L.marker([ac.lat, ac.lon], {
        icon: safeDivIcon({
          className: "",
          html: `<div class="${flashCls}" style="width:32px;height:32px;">
            <img src="${iconUrl}" width="32" height="32" style="display:block;"/>
          </div>`,
          iconSize: [32, 32], iconAnchor: [16, 16],
        }),
        zIndexOffset: isEmerg ? 300 : (isMil ? 200 : (isSel ? 250 : 100)),
      }).addTo(acLayRef.current!);

      // Tooltip
      const tipParts = [cs];
      if (ac.t) tipParts.push(ac.t);
      if (typeof ac.alt_baro === "number") tipParts.push(ac.alt_baro.toLocaleString() + " ft");
      if (isMil) tipParts.push("MIL");
      marker.bindTooltip(sanitizeHtml(tipParts.join(" · ")), { direction: "top" });

      // Click → open detail panel
      marker.on("click", () => {
        setAdsbSelected(ac);
      });
    });

    // Render track trails from history
    adsbFiltered.forEach((ac) => {
      const trail = trackHistory.get(ac.hex);
      if (!trail || trail.length < 2) return;
      for (let i = 0; i < trail.length - 1; i++) {
        const pt = trail[i];
        const next = trail[i + 1];
        const segColor = getAltitudeColor(pt.alt);
        L.polyline(
          [[pt.lat, pt.lon], [next.lat, next.lon]],
          { color: segColor, weight: 2, opacity: 0.5, dashArray: "4 4" },
        ).addTo(acTrackLayRef.current!);
      }
    });
  }, [adsbFiltered, layers.aircraft, adsbSelected, trackHistory]);

  // ── Vessel layer — clean directional markers with click details ───────────
  useEffect(() => {
    if (!vsLayRef.current) return;
    vsLayRef.current.clearLayers();
    if (!layers.vessels) return;

    const NAV_STATUS: Record<number, string> = {
      0: "Under Way (Engine)", 1: "At Anchor", 2: "Not Under Command",
      3: "Restricted Maneuverability", 4: "Constrained by Draught",
      5: "Moored", 6: "Aground", 7: "Fishing", 8: "Under Sail",
      14: "AIS-SART", 15: "Undefined",
    };

    const VESSEL_BOX = { latMin: 8, latMax: 46, lonMin: -6, lonMax: 67 };
    const filtered = vessels.filter((v) =>
      v.lat != null && v.lon != null &&
      v.lat >= VESSEL_BOX.latMin && v.lat <= VESSEL_BOX.latMax &&
      v.lon >= VESSEL_BOX.lonMin && v.lon <= VESSEL_BOX.lonMax
    );

    // Prioritize: named + known type first, then moving, then the rest
    const sorted = [...filtered].sort((a, b) => {
      const aScore = (a.name ? 2 : 0) + (a.ship_type_name && a.ship_type_name !== "Unknown" ? 1 : 0);
      const bScore = (b.name ? 2 : 0) + (b.ship_type_name && b.ship_type_name !== "Unknown" ? 1 : 0);
      return bScore - aScore;
    });

    sorted.slice(0, 800).forEach((v) => {
      const vc  = getVesselColor(v);
      const hdg = v.heading != null && v.heading < 360 ? v.heading : (v.course ?? 0);
      const isMoving = v.speed != null && v.speed > 0.5;
      const isAnchored = v.nav_status === 1 || v.nav_status === 5;
      const isNaval = v.vessel_category === "naval" || v.vessel_category === "government";
      const opacity = isAnchored ? 0.5 : 0.9;
      const cat = v.vessel_category ?? "other";
      const catLabel = VESSEL_CAT_LABELS[cat] ?? "OTHER";

      // Naval vessels get larger markers
      const scale = isNaval ? 1.3 : 1;
      const svg = isMoving
        ? `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-5 -7 10 14" width="${Math.round(12*scale)}" height="${Math.round(16*scale)}">
            <polygon points="0,-6 4,5 0,3 -4,5" fill="${vc}" stroke="rgba(0,0,0,0.5)" stroke-width="0.7" opacity="${opacity}"/>
          </svg>`
        : `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 8 8" width="${Math.round(8*scale)}" height="${Math.round(8*scale)}">
            <circle cx="0" cy="0" r="3" fill="${vc}" stroke="rgba(0,0,0,0.5)" stroke-width="0.6" opacity="${opacity}"/>
          </svg>`;

      const iconW = Math.round((isMoving ? 12 : 8) * scale);
      const iconH = Math.round((isMoving ? 16 : 8) * scale);
      const iconSize: [number, number] = [iconW, iconH];
      const iconAnchor: [number, number] = [Math.round(iconW/2), Math.round(iconH/2)];

      // Tooltip
      const tipParts: string[] = [v.name || v.mmsi];
      if (v.flag_code) tipParts.push(v.flag_code);
      if (cat !== "other") tipParts.push(catLabel);
      if (v.speed != null && v.speed > 0) tipParts.push(`${v.speed.toFixed(1)} kn`);
      if (v.destination) tipParts.push(`→ ${v.destination}`);

      const navLabel = NAV_STATUS[v.nav_status] ?? "";
      const typeLabel = v.ship_type_name && v.ship_type_name !== "Unknown" ? v.ship_type_name : "";
      const flagDisplay = v.flag_name ? `${v.flag_code} · ${v.flag_name}` : (v.flag_code || "");

      const popupHtml = `
        <div style="font-family:var(--font-mono),monospace;font-size:12px;color:#c8d6e5;line-height:1.7;padding:10px 12px;min-width:200px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <span style="font-size:13px;font-weight:700;color:${vc};">${v.name ? v.name.toUpperCase() : "VESSEL " + v.mmsi}</span>
            <span style="font-size:11px;padding:1px 5px;border-radius:2px;font-weight:700;letter-spacing:0.5px;
              background:${vc}22;color:${vc};border:1px solid ${vc}44;">${catLabel}</span>
          </div>
          <div style="color:#5a6a7e;">MMSI: <span style="color:#c8d6e5;">${v.mmsi}</span></div>
          ${v.callsign ? `<div style="color:#5a6a7e;">Call: <span style="color:#c8d6e5;">${v.callsign}</span></div>` : ""}
          ${v.imo ? `<div style="color:#5a6a7e;">IMO: <span style="color:#c8d6e5;">${v.imo}</span></div>` : ""}
          ${flagDisplay ? `<div style="color:#5a6a7e;">Flag: <span style="color:#c8d6e5;">${flagDisplay}</span></div>` : ""}
          ${typeLabel ? `<div style="color:#5a6a7e;">Type: <span style="color:#c8d6e5;">${typeLabel}</span></div>` : ""}
          ${v.speed != null ? `<div style="color:#5a6a7e;">Speed: <span style="color:#c8d6e5;">${v.speed.toFixed(1)} kn</span></div>` : ""}
          ${v.heading != null && v.heading < 360 ? `<div style="color:#5a6a7e;">Heading: <span style="color:#c8d6e5;">${Math.round(v.heading)}°</span></div>` : ""}
          ${v.course != null ? `<div style="color:#5a6a7e;">Course: <span style="color:#c8d6e5;">${Math.round(v.course)}°</span></div>` : ""}
          ${v.destination ? `<div style="color:#5a6a7e;">Dest: <span style="color:#c8d6e5;">${v.destination}</span></div>` : ""}
          ${navLabel ? `<div style="color:#5a6a7e;">Status: <span style="color:#c8d6e5;">${navLabel}</span></div>` : ""}
          ${v.length ? `<div style="color:#5a6a7e;">Length: <span style="color:#c8d6e5;">${v.length}m</span></div>` : ""}
          <div style="color:#5a6a7e;">Pos: <span style="color:#c8d6e5;">${v.lat.toFixed(4)}°N, ${v.lon.toFixed(4)}°E</span></div>
          <div style="margin-top:6px;font-size:11px;color:#8b9eaf;">Source: AIS (AISStream) · real-time WebSocket</div>
        </div>
      `;

      L.marker([v.lat, v.lon], {
        icon: safeDivIcon({
          className: "",
          html: `<div style="width:${iconSize[0]}px;height:${iconSize[1]}px;transform:rotate(${hdg}deg);
              transform-origin:center;filter:drop-shadow(0 0 2px ${vc});">${svg}</div>`,
          iconSize,
          iconAnchor,
        }),
        zIndexOffset: isNaval ? 110 : 90,
      }).addTo(vsLayRef.current!)
        .bindTooltip(sanitizeHtml(tipParts.join(" · ")), { direction: "top" })
        .bindPopup(sanitizeHtml(popupHtml), { maxWidth: 280, closeButton: true });
    });
  }, [vessels, layers.vessels]);

  // ── Navigation anomalies zones ────────────────────────────────────────────────────
  useEffect(() => {
    if (!jzLayRef.current) return;
    jzLayRef.current.clearLayers();
    if (!layers.jamming) return;
    jammingZones.filter((z) => z.lat != null && z.lon != null).forEach((z) => {
      L.circle([z.lat, z.lon], {
        radius: z.radius_km * 1000, color: "#ff4040", fillColor: "#ff2020",
        weight: 2, fillOpacity: 0.04 + z.intensity * 0.08, dashArray: "8 6",
        opacity: 0.75,
      }).addTo(jzLayRef.current!).bindTooltip(
        sanitizeHtml(`⚡ NAV QUALITY ANOMALY · ${z.aircraft_count} AC affected · intensity ${(z.intensity * 10).toFixed(0)}/10 · r=${z.radius_km.toFixed(0)}km`),
        { direction: "top", permanent: false },
      );
    });
  }, [jammingZones, layers.jamming]);

  // ── Reset view to conflict theater ───────────────────────────────────────
  const resetView = () => {
    mapRef.current?.setView([30, 45], 6, { animate: true, duration: 0.8 });
  };

  // ── Toggle helpers ───────────────────────────────────────────────────────
  const toggleType = (type: string) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type); else next.add(type);
      return next;
    });
  };
  const toggleLayer = (key: keyof LayerState) => {
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="panel" style={{ gridArea: "map", position: "relative", overflow: "hidden", minHeight: 0, height: "100%" }}>
      <div ref={divRef} style={{ position: "absolute", inset: 0 }} />

      {/* ── Filter Panel (left side) ── */}
      {/* pointer-events: none on outer wrapper so transparent areas pass through to the map */}
      <div style={{
        position: "absolute", top: 10, left: 10, zIndex: 1001,
        display: "flex", flexDirection: "column", gap: 0,
        fontFamily: "var(--font-mono)", fontSize: 11,
        pointerEvents: "none",
      }}>
        {/* Toggle button */}
        <button
          onClick={() => setFilterOpen((o) => !o)}
          style={{
            background: "rgba(6,10,15,0.92)", border: "1px solid rgba(88,166,255,.25)",
            borderRadius: "3px 3px 0 0", color: "#58a6ff",
            padding: "4px 10px", cursor: "pointer",
            fontSize: 11, letterSpacing: 1.5, fontFamily: "var(--font-mono)",
            display: "flex", alignItems: "center", gap: 6,
            pointerEvents: "auto",
          }}
        >
          <span style={{ fontSize: 11 }}>{filterOpen ? "◀" : "▶"}</span>
          FILTERS
        </button>

        {filterOpen && (
          <div style={{
            background: "rgba(6,10,15,0.92)",
            border: "1px solid rgba(88,166,255,.2)",
            borderTop: "none",
            borderRadius: "0 0 3px 3px",
            padding: "10px 12px",
            minWidth: 170,
            display: "flex", flexDirection: "column", gap: 8,
            pointerEvents: "auto",
          }}>
            {/* Event Types */}
            <div style={{ letterSpacing: 2, color: "#8b9eaf", fontSize: 11, fontWeight: 700, marginBottom: 2 }}>
              EVENT TYPES
            </div>
            {Object.entries(EVENT_TYPE_CONFIG).map(([type, cfg]) => (
              <label key={type} style={{
                display: "flex", alignItems: "center", gap: 7,
                cursor: "pointer", userSelect: "none",
                opacity: activeTypes.has(type) ? 1 : 0.4,
              }}>
                <input
                  type="checkbox"
                  checked={activeTypes.has(type)}
                  onChange={() => toggleType(type)}
                  style={{ display: "none" }}
                />
                {type === "military" ? (
                  // Mini explosion starburst to match the map marker
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="-12 -12 24 24" width="11" height="11"
                    style={{ flexShrink: 0, filter: activeTypes.has(type) ? `drop-shadow(0 0 2px ${cfg.color})` : "none" }}>
                    <polygon
                      points="0,-10 1.5,-3.7 7.1,-7.1 3.7,-1.5 10,0 3.7,1.5 7.1,7.1 1.5,3.7 0,10 -1.5,3.7 -7.1,7.1 -3.7,1.5 -10,0 -3.7,-1.5 -7.1,-7.1 -1.5,-3.7"
                      fill={activeTypes.has(type) ? cfg.color : "transparent"} stroke={cfg.color} strokeWidth="1.5"/>
                    <circle cx="0" cy="0" r="2.5" fill="#fff" opacity={activeTypes.has(type) ? 0.9 : 0}/>
                  </svg>
                ) : (
                  <div style={{
                    width: 10, height: 10,
                    background: activeTypes.has(type) ? cfg.color : "transparent",
                    border: `1.5px solid ${cfg.color}`,
                    borderRadius: type === "cyber" ? 0 : "50%",
                    flexShrink: 0,
                    boxShadow: activeTypes.has(type) ? `0 0 5px ${cfg.color}88` : "none",
                  }} />
                )}
                <span style={{ color: activeTypes.has(type) ? "#b0bec5" : "#96a8b8", fontSize: 11 }}>
                  {cfg.icon} {cfg.label}
                </span>
              </label>
            ))}

            {/* Infrastructure Layers */}
            <div style={{ letterSpacing: 2, color: "#8b9eaf", fontSize: 11, fontWeight: 700,
              marginTop: 6, paddingTop: 6, borderTop: "1px solid rgba(88,166,255,.1)" }}>
              INFRASTRUCTURE
            </div>
            {(
              [
                ["bases",        "▲", "#58a6ff", "Key Bases"],
                ["chokepoints",  "⚓", "#d29922", "Chokepoints"],
                ["refineries",   "⛽", "#d29922", "Refineries"],
                ["airfields",    "✈", "#7ab8d4", "All Airfields"],
                ["oilPipelines", "▬", "#d29922", "Oil Pipelines"],
                ["gasPipelines", "▬", "#58a6ff", "Gas Pipelines"],
              ] as [keyof LayerState, string, string, string][]
            ).map(([key, icon, col, label]) => (
              <label key={key} style={{
                display: "flex", alignItems: "center", gap: 7,
                cursor: "pointer", userSelect: "none",
                opacity: layers[key] ? 1 : 0.4,
              }}>
                <input
                  type="checkbox"
                  checked={layers[key]}
                  onChange={() => toggleLayer(key)}
                  style={{ display: "none" }}
                />
                <div style={{
                  width: 10, height: 10,
                  background: layers[key] ? col + "44" : "transparent",
                  border: `1.5px solid ${col}`,
                  borderRadius: 2,
                  flexShrink: 0,
                }} />
                <span style={{ color: layers[key] ? "#b0bec5" : "#96a8b8", fontSize: 11 }}>
                  {icon} {label}
                </span>
              </label>
            ))}

            {/* Live Overlays */}
            <div style={{ letterSpacing: 2, color: "#8b9eaf", fontSize: 11, fontWeight: 700,
              marginTop: 6, paddingTop: 6, borderTop: "1px solid rgba(88,166,255,.1)" }}>
              LIVE OVERLAYS
            </div>
            {(
              [
                ["aircraft", "✈", "#58d0ff", `Aircraft (${adsbFiltered.length})`],
                ["vessels",  "▲", "#40e0d0", `Vessels (${vessels.length})`],
                ["jamming",  "⚡", "#ff4040", `Navigation anomalies (${jammingZones.length})`],
              ] as [keyof LayerState, string, string, string][]
            ).map(([key, icon, col, label]) => (
              <label key={key} style={{
                display: "flex", alignItems: "center", gap: 7,
                cursor: "pointer", userSelect: "none",
                opacity: layers[key] ? 1 : 0.4,
              }}>
                <input
                  type="checkbox"
                  checked={layers[key]}
                  onChange={() => toggleLayer(key)}
                  style={{ display: "none" }}
                />
                <div style={{
                  width: 10, height: 10,
                  background: layers[key] ? col + "44" : "transparent",
                  border: `1.5px solid ${col}`,
                  borderRadius: 2, flexShrink: 0,
                }} />
                <span style={{ color: layers[key] ? "#b0bec5" : "#96a8b8", fontSize: 11 }}>
                  {icon} {label}
                </span>
              </label>
            ))}
          </div>
        )}
      </div>




      {/* ── ADS-B Detail Panel (left side, above filter) ── */}
      <AircraftDetailPanel
        aircraft={adsbSelected}
        onClose={() => setAdsbSelected(null)}
      />



      {/* ── Reset view button (bottom-left of map) ── */}
      <button
        onClick={resetView}
        title="Reset to conflict theater"
        style={{
          position: "absolute", bottom: 10, left: 10, zIndex: 1001,
          background: "rgba(6,10,15,0.9)", border: "1px solid rgba(88,166,255,.25)",
          borderRadius: 3, color: "#58a6ff", padding: "4px 9px",
          cursor: "pointer", fontSize: 11, letterSpacing: 1.5,
          fontFamily: "var(--font-mono)",
        }}
      >
        ⊕ RESET VIEW
      </button>

      {/* ── Verified Reports — floating collapsible panel (top-right, below zoom) ── */}

      {/* ── Status overlay ── */}
      <div style={{
        position: "absolute", top: 10, left: filterOpen ? 210 : 90, zIndex: 1000,
        pointerEvents: "none",
      }}>
        {geoEvents.length === 0 && (
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: 2,
            color: "#d29922", padding: "4px 10px",
            background: "rgba(6,10,15,0.85)",
            border: "1px solid rgba(210,153,34,.3)", borderRadius: 2,
          }}>
            ⚠ AWAITING INTELLIGENCE EVENTS
          </div>
        )}
        {geoEvents.length > 0 && (
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: 1.5,
            color: "#3fb950", padding: "3px 8px",
            background: "rgba(6,10,15,0.8)",
            border: "1px solid rgba(63,185,80,.2)", borderRadius: 2,
          }}>
            ● {geoEvents.length} EVENTS PLOTTED
          </div>
        )}
      </div>
    </div>
  );
}
