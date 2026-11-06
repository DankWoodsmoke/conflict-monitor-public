import type { ConflictEvent } from "../types/event";

type AssessmentEvent=Pick<ConflictEvent,"severity"> & Partial<Pick<ConflictEvent,"synthetic"|"evidence"|"classification_status"|"event_type">>;
const validScore=(value:unknown):value is number=>typeof value==="number"&&Number.isInteger(value)&&value>=1&&value<=10;

/** Only source-bound model estimates or explicitly synthetic ratings can be ranked.
 * A legacy number stays visible as historical metadata, never an alert verdict. */
export function assessedSeverity(event:AssessmentEvent):number|null {
  if(!validScore(event.severity))return null;
  if(event.synthetic===true)return event.severity;
  const a=event.evidence?.assessment;
  return event.classification_status==="extracted"&&a?.status==="model_estimate"&&
    a.basis==="source_bound_model_extraction"&&a.review_status==="unreviewed"&&a.confirmed===false&&
    a.severity===event.severity&&typeof a.model==="string"&&a.model.trim().length>0&&
    typeof a.rubric_version==="string"&&a.rubric_version.trim().length>0&&
    typeof a.source_sha256==="string"&&/^[0-9a-f]{64}$/i.test(a.source_sha256)?event.severity:null;
}
export function isScored(event:AssessmentEvent):boolean{return assessedSeverity(event)!==null;}
export function severityLabel(event:AssessmentEvent):string {
  if(event.synthetic===true&&validScore(event.severity))return `EXERCISE ${event.severity}/10`;
  if(isScored(event))return `MODEL ${event.severity}/10 · UNREVIEWED`;
  if(event.evidence?.assessment?.status==="sensor_not_applicable")return "NOT RATED · SENSOR";
  if(event.evidence?.assessment?.status==="invalid"||event.classification_status==="invalid")return "INVALID ASSESSMENT";
  return validScore(event.severity)?`LEGACY ${event.severity}/10 · UNREVIEWED`:"UNSCORED";
}
/** Current live contracts never qualify a critical alert. Showcase is explicit. */
export function hasCriticalAlertStyle(event:AssessmentEvent):boolean {
  return event.synthetic===true&&(assessedSeverity(event)??0)>=9;
}
export function averageSeverity(events: ConflictEvent[]): number | null {
  const scored=events.filter(isScored);
  const bases=new Set(scored.map(e=>e.synthetic===true?"synthetic":`${e.evidence!.assessment!.model}|${e.evidence!.assessment!.rubric_version}`));
  if(bases.size>1)return null;
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
