import type { ConflictEvent } from "../types/event";
import { safeUrl } from "../lib/runtime";
import {PlaceMentionReview} from "./PlaceMentionReview";
import {severityLabel} from "../lib/events";

export function EvidenceDetails({event}:{event:ConflictEvent}) {
  return <details className="evidence-details" onClick={e=>e.stopPropagation()}>
    <summary>Evidence & provenance</summary>
    <dl><dt>Assessment</dt><dd>{(event.evidence?.status || "unassessed").replace(/_/g," ")}</dd>
      <dt>Original sources</dt><dd>{event.evidence?.unique_source_count ?? "Unknown"}</dd>
      <dt>Independence</dt><dd>{event.evidence?.independence_status || "Unassessed"}</dd>
      <dt>Classification</dt><dd>{event.classification_status === "not_requested" ? "Source report · model not requested" : event.classification_status || "Legacy / unknown"}</dd>
      <dt>Severity assessment</dt><dd>{severityLabel(event)}</dd>
      <dt>Assessment basis</dt><dd>{event.synthetic ? "Synthetic exercise" : (event.evidence?.assessment?.basis || "Provenance unavailable").replace(/_/g," ")}</dd>
      <dt>Model / rubric</dt><dd>{event.evidence?.assessment?.model || "Not recorded"} / {event.evidence?.assessment?.rubric_version || "Not recorded"}</dd>
      <dt title="Publication, update or sensor acquisition, depending on the source">Source time</dt><dd>{new Date(event.timestamp).toLocaleString()} · incident time unverified</dd>
      <dt>Location precision</dt><dd>{event.geolocation_precision || "Unknown"}</dd></dl>
    <p>Publisher ratings and repeated reports do not verify a claim. Location uncertainty is not calibrated.</p>
    <p>Severity, confidence and urgency are separate. An unreviewed model or legacy score is not a confirmed critical alert.</p>
    {(event.evidence?.assessment?.limitations || []).map((text,i)=><p key={`assessment-${i}`}>{text}</p>)}
    {(event.evidence?.limitations || []).map((text,i)=><p key={i}>{text}</p>)}
    {event.reports?.map((report,i)=>{const url=safeUrl(report.source_url);return url?<a key={i} href={url} target="_blank" rel="noopener noreferrer">Original report {i+1} ↗</a>:null;})}
    <details><summary>Preserved source text</summary><p>{event.raw_text}</p></details>
    <PlaceMentionReview key={`${event.id}:${event.raw_text}`} event={event}/>
  </details>;
}
