import type { ConflictEvent } from "../types/event";
import { safeUrl } from "../lib/runtime";

export function EvidenceDetails({event}:{event:ConflictEvent}) {
  return <details className="evidence-details" onClick={e=>e.stopPropagation()}>
    <summary>Evidence & provenance</summary>
    <dl><dt>Assessment</dt><dd>{(event.evidence?.status || "unassessed").replace(/_/g," ")}</dd>
      <dt>Original sources</dt><dd>{event.evidence?.unique_source_count ?? "Unknown"}</dd>
      <dt>Independence</dt><dd>{event.evidence?.independence_status || "Unassessed"}</dd>
      <dt>Classification</dt><dd>{event.classification_status === "not_requested" ? "Source report · model not requested" : event.classification_status || "Legacy / unknown"}</dd>
      <dt>Source publication</dt><dd>{new Date(event.timestamp).toLocaleString()} · incident time unverified</dd>
      <dt>Location precision</dt><dd>{event.geolocation_precision || "Unknown"}</dd></dl>
    <p>Publisher ratings and repeated reports do not verify a claim. Location uncertainty is not calibrated.</p>
    {(event.evidence?.limitations || []).map((text,i)=><p key={i}>{text}</p>)}
    {event.reports?.map((report,i)=>{const url=safeUrl(report.source_url);return url?<a key={i} href={url} target="_blank" rel="noopener noreferrer">Original report {i+1} ↗</a>:null;})}
    <details><summary>Preserved source text</summary><p>{event.raw_text}</p></details>
  </details>;
}
