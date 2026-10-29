import type { ConflictEvent } from "../types/event";

/** Zero is the explicit free-report sentinel, never a low impact assessment. */
export function isScored(event: Pick<ConflictEvent,"severity">): boolean {
  return Number.isFinite(event.severity) && event.severity >= 1 && event.severity <= 10;
}
export function severityLabel(event: Pick<ConflictEvent,"severity">): string {
  return isScored(event) ? `${event.severity}/10` : "UNSCORED";
}
export function averageSeverity(events: ConflictEvent[]): number | null {
  const scored=events.filter(isScored);
  return scored.length ? scored.reduce((sum,e)=>sum+e.severity,0)/scored.length : null;
}

export function reportSourceKind(event:Pick<ConflictEvent,"source"|"event_type">):"telegram"|"x"|"rss"|"sensor"|"other"{
 const source=event.source||"";
 if(event.event_type==="thermal_anomaly"||source==="satellite_firms")return "sensor";
 if(source==="telegram")return "telegram";
 if(source.startsWith("rss_x_")||source.startsWith("x_"))return "x";
 if(source.startsWith("rss_"))return "rss";
 return "other";
}
