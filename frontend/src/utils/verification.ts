
import type { ConflictEvent } from "../types/event";

// Multiple source records remain distinct from independent observation.

export function getNetworks(evt: ConflictEvent): string[] {
  if (evt.evidence?.source_networks) return [...new Set(evt.evidence.source_networks)];
  if (evt.confirmed_networks && evt.confirmed_networks.trim()) {
    return evt.confirmed_networks.split(",").map(n => n.trim()).filter(Boolean);
  }
  return [];
}


export function hasMultipleReports(evt: ConflictEvent): boolean {
  return evt.evidence?.status === "multiple_reports" && evt.evidence.unique_source_count >= 2;
}


export function isViralAmplification(evt: ConflictEvent): boolean {
  return (evt.report_count ?? 1) >= 4 && !hasMultipleReports(evt);
}


export const NETWORK_META: Record<string, { short: string; color: string; tip: string }> = {
  TG:           { short: "TG",    color: "#4dabf7", tip: "Telegram OSINT (pro-resistance lean)" },
  X_OSINT:      { short: "X",     color: "#74c0fc", tip: "X/Twitter OSINT analysts" },
  WEST_PRESS:   { short: "PRESS", color: "#69db7c", tip: "Western editorial press (BBC, Guardian, DW, War Zone, Defense One, Iran International)" },
  MIDEAST_PRESS:{ short: "ME",    color: "#ffd43b", tip: "Non-Western editorial (Al Jazeera, RFI, Middle East Eye)" },
  IL_PRESS:     { short: "IL",    color: "#a9e34b", tip: "Israeli press (Times of Israel, Jerusalem Post, Haaretz)" },
  MARITIME_SEC: { short: "MAR",   color: "#22d3ee", tip: "Official maritime security (UKMTO, US 5th Fleet, Combined Maritime Forces, TankerTrackers)" },
  ANALYSIS:     { short: "ANL",   color: "#a78bfa", tip: "Macro-economic & strategic analysis (Lyn Alden, Luke Gromen, Ian Bremmer, Raoul Pal, Michael Pettis, Chris Martenson, CSIS, Eurasia Group, War on the Rocks, FreightWaves)" },
};
