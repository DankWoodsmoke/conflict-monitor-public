import {useEffect,useRef,useState} from "react";
import type {ConflictEvent} from "../types/event";
import {apiFetch} from "../lib/api";
import {API_BASE,SHOWCASE} from "../lib/runtime";
import {validatePlaceReview} from "./PlaceMentionReview";

interface Props {event:ConflictEvent;operatorKey?:string;onConfigureOperator?:()=>void}
type Mention={text:string;start_utf16:number;end_utf16:number;status:string};
type Report={id:number;text:string;relevance:"relevant"|"not_relevant"|"uncertain";stance:"reported"|"denied"|"uncertain";mentions:Record<string,Mention[]>};
type Result={source:{id:number;text:string;source:string;source_platform:string;channel_name:string;source_url:string;published_at:string;original_text_sha256:string};
 report:Report;place_review:Awaited<ReturnType<typeof validatePlaceReview>>;
 provenance:{model:string;model_digest:string;system_sha256:string};model_excerpt_characters:number};
type Job={job_id:string;event_id:number;source_sha256:string;status:string;status_url:string;created_at:string;retention_seconds:3600;result?:Result};
const HASH=/^[a-f0-9]{64}$/,UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const states=["queued","running","available","source_changed","source_permission_required","failed","cancelled"];
const object=(value:unknown):Record<string,unknown>=>{if(!value||typeof value!=="object"||Array.isArray(value))throw Error("Invalid local analysis response");return value as Record<string,unknown>;};
const small=(value:unknown,max=300):value is string=>typeof value==="string"&&value.length>0&&value.length<=max;
async function hash(text:string){const data=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(text));return [...new Uint8Array(data)].map(b=>b.toString(16).padStart(2,"0")).join("");}

/** Literal identity gates do not establish semantic truth or incident location. */
export async function validateReportAnalysis(value:unknown,event:ConflictEvent,expectedHash:string,expectedJob?:string):Promise<Job>{
 const job=object(value);
 if(!small(job.job_id,36)||!UUID.test(job.job_id)||expectedJob&&job.job_id!==expectedJob||job.event_id!==event.id||job.source_sha256!==expectedHash||!small(job.status)||!states.includes(job.status)||job.status_url!==`/report-analysis/jobs/${job.job_id}`)throw Error("Analysis does not match this source request");
 if(typeof job.created_at!=="string"||!Number.isFinite(Date.parse(job.created_at))||Date.parse(job.created_at)>Date.now()+5000||job.retention_seconds!==3600)throw Error("Invalid local result expiry");
 if(Date.now()>=Date.parse(job.created_at)+3600000)throw Error("This local result expired. Analyze again to create a new proposal.");
 if(job.status!=="available"){
  if(job.result!==undefined)throw Error("Incomplete analysis contains a result");
  return job as unknown as Job;
 }
 const result=object(job.result),source=object(result.source),report=object(result.report),provenance=object(result.provenance);
 const excerpt=Array.from(event.raw_text).slice(0,2500).join("");
 if(result.contract_version!=="selected-report-local-analysis-v1"||result.coordinates!==null||result.severity!==null||result.critical_alert_eligible!==false||result.mutates_events!==false||
  source.id!==event.id||source.text!==event.raw_text||!small(source.source)||source.source_platform!==event.source||source.channel_name!==(event.channel_name||"")||source.source_url!==event.source_url||
  typeof source.published_at!=="string"||!Number.isFinite(Date.parse(source.published_at))||Date.parse(source.published_at)!==Date.parse(event.timestamp)||source.original_text_sha256!==expectedHash||
  result.model_excerpt_sha256!==await hash(excerpt)||result.model_excerpt_characters!==Array.from(excerpt).length||!small(result.source_snapshot_sha256,64)||!HASH.test(result.source_snapshot_sha256)||
  report.id!==event.id||report.text!==excerpt||report.original_text_sha256!==expectedHash||report.source_url!==source.source_url||report.source_platform!==source.source_platform||
  report.coordinates!==null||report.severity!==null||report.assessment_status!=="model_generated_unreviewed"||
  typeof report.relevance!=="string"||!["relevant","not_relevant","uncertain"].includes(report.relevance)||typeof report.stance!=="string"||!["reported","denied","uncertain"].includes(report.stance)||
  !small(provenance.model,100)||!small(provenance.model_digest,64)||!HASH.test(provenance.model_digest)||!small(provenance.system_sha256,64)||!HASH.test(provenance.system_sha256))throw Error("Invalid or changed source-bound proposal");
 const mentions=object(report.mentions);
 for(const key of ["place_mentions","actor_mentions","quantity_mentions"]){
  const rows=mentions[key];if(!Array.isArray(rows)||rows.length>6)throw Error("Invalid source mentions");
  const seen=new Set<string>();
  for(const item of rows){const mention=object(item),start=mention.start_utf16,end=mention.end_utf16;
   if(!small(mention.text,160)||seen.has(mention.text)||typeof start!=="number"||typeof end!=="number"||!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start<0||end<=start||end>excerpt.length||excerpt.slice(start,end)!==mention.text||mention.status!==(key==="place_mentions"?"source_mention_not_event_location":"source_mention_unverified"))throw Error("Invalid literal source span");
   seen.add(mention.text);
  }
 }
 const review=await validatePlaceReview({...object(result.place_review),event_id:event.id},event);
 return {...job,result:{...result,place_review:review}} as unknown as Job;
}

function failure(status:string){return status==="source_changed"?"The source or its provenance changed. Refresh the report before analyzing it again.":status==="source_permission_required"?"This source requires permission for AI processing. No proposal is shown.":status==="cancelled"?"Local analysis was cancelled. No proposal is shown.":"Local analysis did not produce a validated proposal. The source report is unchanged.";}

function SelectedReportAnalysis({event,operatorKey="",onConfigureOperator}:Props){
 const [open,setOpen]=useState(false),[enabled,setEnabled]=useState(false),[model,setModel]=useState(""),[message,setMessage]=useState(""),[busy,setBusy]=useState(false),[result,setResult]=useState<Result|null>(null);
 const current=useRef<AbortController|null>(null),timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined),expiryTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined),job=useRef<{id:string;hash:string}|null>(null),running=useRef(false),resultOwner=useRef("");
 const pollRef=useRef<((id:string,sourceHash:string)=>Promise<void>)|null>(null);
 useEffect(()=>{
  const controller=new AbortController();current.current=controller;clearTimeout(timer.current);clearTimeout(expiryTimer.current);running.current=false;setBusy(false);setResult(null);
  if(!open||SHOWCASE)return()=>controller.abort();
  let deadline=Date.now()+300000;
  const active=()=>current.current===controller&&!controller.signal.aborted;
  const poll=async(id:string,sourceHash:string)=>{
   if(!active())return;
   try{
    const response=await apiFetch(`${API_BASE}/report-analysis/jobs/${id}`,{headers:{"X-Admin-Key":operatorKey},signal:controller.signal});
    if(!response.ok)throw Error(response.status===404?"This local result expired or the server restarted. Analyze again to create a new proposal.":response.status===403?"Operator access was rejected.":"Local analysis status is unavailable; no automatic retry was made.");
    const checked=await validateReportAnalysis(await response.json(),event,sourceHash,id);
    if(!active())return;
    if(["queued","running"].includes(checked.status)){
     setBusy(true);setMessage("Analyzing this source locally…");
     if(Date.now()>deadline){setBusy(false);setMessage("Stopped watching after five minutes. The local job may still finish; reopen this panel to check it.");return;}
     timer.current=setTimeout(()=>void poll(id,sourceHash),1500);return;
    }
    setBusy(false);running.current=false;
    if(checked.status==="available"){
     resultOwner.current=operatorKey;setResult(checked.result!);setMessage("Local proposal ready · unreviewed");
     const remaining=Date.parse(checked.created_at)+checked.retention_seconds*1000-Date.now();
     expiryTimer.current=setTimeout(()=>{if(active()){setResult(null);job.current=null;setMessage("This local result expired. Analyze again to create a new proposal.");}},Math.max(0,remaining));
    }
    else{setResult(null);setMessage(failure(checked.status));job.current=null;}
   }catch(error){if(active()){setBusy(false);running.current=false;setResult(null);setMessage(error instanceof Error?error.message:"Local analysis unavailable");}}
  };
  pollRef.current=poll;
  void (async()=>{
   try{
    const response=await apiFetch(`${API_BASE}/briefing/status`,{signal:controller.signal});
    if(!response.ok)throw Error("Local tool availability could not be checked.");
    const status=object(object(await response.json()).local_ai);
    if(typeof status.enabled!=="boolean"||status.model!==null&&!small(status.model,100))throw Error("Invalid local tool availability");
    if(!active())return;
    setEnabled(status.enabled);setModel(typeof status.model==="string"?status.model:"");
    if(!status.enabled)setMessage("Local analysis is disabled by the operator.");
    if(job.current&&operatorKey){running.current=true;setBusy(true);deadline=Date.now()+300000;void poll(job.current.id,job.current.hash);}
   }catch(error){if(active()){setEnabled(false);setMessage(error instanceof Error?error.message:"Local tools unavailable");}}
  })();
  return()=>{controller.abort();clearTimeout(timer.current);clearTimeout(expiryTimer.current);pollRef.current=null;};
 },[open,operatorKey]);

 async function run(){
  if(!open||SHOWCASE||!enabled||running.current)return;
  if(!operatorKey.trim()){onConfigureOperator?.();return;}
  const controller=current.current;if(!controller||controller.signal.aborted)return;
  const active=()=>current.current===controller&&!controller.signal.aborted;
  running.current=true;clearTimeout(timer.current);clearTimeout(expiryTimer.current);setBusy(true);setResult(null);setMessage("Binding the preserved source…");job.current=null;
  try{
   const sourceHash=await hash(event.raw_text);if(!active())return;
   const response=await apiFetch(`${API_BASE}/report-analysis/${event.id}`,{method:"POST",headers:{"Content-Type":"application/json","X-Admin-Key":operatorKey},body:JSON.stringify({expected_source_sha256:sourceHash}),signal:controller.signal});
   if(!active())return;
   if(response.status!==202){const body=object(await response.json().catch(()=>({}))),detail=body.detail&&typeof body.detail==="object"?object(body.detail):{};throw Error(detail.code==="SourcePermissionRequired"?failure("source_permission_required"):detail.code==="SourceChanged"?failure("source_changed"):response.status===409?"Another local analysis is already running. No duplicate request was started.":response.status===403?"Operator access was rejected.":response.status===422?"This source is stale, missing raw text, or ineligible for local analysis.":"Local analysis could not be started.");}
   const checked=await validateReportAnalysis(await response.json(),event,sourceHash);
   if(!active())return;
   if(checked.status!=="queued")throw Error("Invalid queue acknowledgement");
   job.current={id:checked.job_id,hash:sourceHash};setMessage("Analyzing this source locally…");await pollRef.current?.(checked.job_id,sourceHash);
  }catch(error){if(active()){running.current=false;setBusy(false);setMessage(error instanceof Error?error.message:"Local analysis unavailable");}}
 }

 return <details className="evidence-details report-analysis" open={open} onToggle={event=>{if(event.target!==event.currentTarget||event.currentTarget.open===open)return;setResult(null);setMessage(event.currentTarget.open?"Checking local tools and current source…":"");setOpen(event.currentTarget.open);}} onClick={event=>event.stopPropagation()}>
  <summary>Analyze this report locally</summary>
  {open&&<section aria-label="Selected report local analysis" style={{display:"grid",gap:8,overflowWrap:"anywhere"}}>
   <p>Review the topic, wording and literal source mentions with {model||"a local model"}. Proposals remain unreviewed; this does not assign severity or move markers.</p>
   {SHOWCASE?<p>Synthetic showcase · local inference is disconnected.</p>:<button type="button" style={{minHeight:44}} disabled={!enabled||busy||!event.raw_text||event.synthetic} onClick={()=>void run()}>{busy?"Working locally…":operatorKey?"Analyze this source":"Configure operator access"}</button>}
   {message&&<p role="status">{message}</p>}
   {result&&resultOwner.current===operatorKey&&<>
    <p><strong>Topic proposal:</strong> {result.report.relevance.replace(/_/g," ")} · <strong>Wording:</strong> {result.report.stance}</p>
    <p>These labels describe source wording; they do not establish that an incident occurred.</p>
    {([['place_mentions','Model place mentions'],['actor_mentions','Actors quoted'],['quantity_mentions','Quantities quoted']] as const).map(([key,label])=><p key={key}><strong>{label}:</strong> {result.report.mentions[key].map(mention=>mention.text).join(" · ")||"None returned"}</p>)}
    <details><summary>Inspect exact source excerpt</summary><p style={{whiteSpace:"pre-wrap"}}>{result.report.text}</p>{result.report.text!==result.source.text&&<p>Only the first {result.model_excerpt_characters} source characters were supplied to the model.</p>}</details>
    <div><strong>Literal place review · no incident location established</strong>
     {result.place_review.markup_incomplete&&<p>Ambiguous markup was excluded; coverage is incomplete.</p>}
     {result.place_review.mentions.length?<ul>{result.place_review.mentions.map(mention=><li key={mention.mention_id}>{mention.span.text} · {mention.status==="disambiguation_required"?"Ambiguous place; review required":"Unreviewed source mention"}<blockquote>{event.raw_text.slice(Math.max(0,mention.span.start_utf16-65),mention.span.start_utf16)}<mark>{mention.span.text}</mark>{event.raw_text.slice(mention.span.end_utf16,mention.span.end_utf16+65)}</blockquote></li>)}</ul>:<p>No names matched the limited local inventory. That does not establish the absence of a place.</p>}
     {result.place_review.truncated&&<p>Only the first 24 mentions are shown.</p>}
    </div>
    <details><summary>Source and model provenance</summary><p>Source #{result.source.id} · {result.source.source}</p><p>Raw source SHA256: {result.source.original_text_sha256}</p><p>Model: {result.provenance.model}</p><p>Model digest: {result.provenance.model_digest}</p><p>No event fields were changed. Results expire after one hour or a server restart.</p></details>
   </>}
  </section>}
 </details>;
}

export function ReportAnalysis(props:Props){
 // Replace the entire observer on source/provenance change, retiring every old
 // request and result before the new selection can display an old proposal.
 const e=props.event;
 const identity=JSON.stringify([e.id,e.raw_text,e.source,e.channel_name,e.source_url,e.timestamp,e.reports||[]]);
 return <SelectedReportAnalysis key={identity} {...props}/>;
}
