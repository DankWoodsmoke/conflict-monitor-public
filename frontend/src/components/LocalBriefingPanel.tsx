import {useEffect,useMemo,useRef,useState,type CSSProperties} from "react";
import {apiFetch} from "../lib/api";
import {API_BASE,SHOWCASE} from "../lib/runtime";
import {parseCaptionPlan,prepareBriefingCaptions,type CaptionPlan} from "../lib/briefingCaptions";

type Mode="analysis"|"video"|"all";
type Job="analyze"|"video";
interface RuntimeState {enabled:boolean;state:string;error_type?:string|null;model?:string|null;voice_configured?:boolean}
interface Status {local_ai:RuntimeState;video:RuntimeState}
interface Mention {text:string;start:number;end:number;status:string}
interface Report {id:number;source:string;published_at:string;source_url:string;text:string;headline:string;
 relevance:"relevant"|"not_relevant"|"uncertain";stance:"reported"|"denied"|"uncertain";
 mentions:Record<string,Mention[]>;text_truncated?:boolean}
interface Analysis {status:string;generated_at?:string;stale?:boolean;reports:Report[];
 provenance?:{model?:string;model_digest?:string};semantic_entailment?:string}
interface Video {status:string;filename?:string;generated_at?:string;stale?:boolean;duration_seconds?:number;
 sources?:Array<{id:number;source:string;source_url:string;published_at:string}>;sha256?:string;segments?:unknown;validation?:unknown}
interface Props {eventIds?:number[];operatorKey?:string;onConfigureOperator?:()=>void;mode?:Mode}

const box:CSSProperties={border:"1px solid #28434e",borderRadius:8,padding:14,background:"#0b1720",minWidth:0};
const button:CSSProperties={minHeight:44,padding:"8px 12px",border:"1px solid #40716e",borderRadius:5,background:"#173b3b",color:"#c8f4ec",cursor:"pointer"};
const stateText=(state:RuntimeState|undefined)=>!state?"Checking availability":!state.enabled?"Disabled by operator":state.state==="failed"?(state.error_type==="SourcePermissionRequired"?"Source permission required · no AI or speech work was started":state.error_type==="NoEligibleSources"?"No eligible recent source reports available":`Failed (${state.error_type||"unknown error"})`):state.state==="running"?"Working locally":state.state==="ready"?"Ready":"Available locally";

function sourceUrl(value:unknown):string {
 if(typeof value!=="string"||value.length>3000)return "";
 try{const u=new URL(value);return ["http:","https:"].includes(u.protocol)&&!u.username&&!u.password?u.href:"";}catch{return "";}
}
function date(value:unknown):string {const ms=typeof value==="string"?Date.parse(value):NaN;return Number.isFinite(ms)?new Date(ms).toISOString().replace("T"," ").replace(/\.\d{3}Z$/," UTC"):"Time unavailable";}

export function videoSource(value:Video):string {
 // Build from the validated content name and configured API origin. Never load
 // an arbitrary external URL supplied in a manifest or report.
 return value.status==="available"&&/^[a-f0-9]{32}\.mp4$/.test(value.filename||"")
  ?`${API_BASE}/briefing/video/${value.filename}`:"";
}

function analysisResult(value:unknown):Analysis {
 const v=value as Analysis;
 if(!v||typeof v!=="object"||!Array.isArray(v.reports)||v.reports.length>8)throw Error("Invalid analysis response");
 if(v.status!=="available")return {status:v.status==="source_permission_required"?v.status:"unavailable",reports:[]};
 if(!v.reports.length||!v.reports.every(r=>r&&Number.isSafeInteger(r.id)&&r.id>0&&
  typeof r.text==="string"&&r.text.length<=12000&&typeof r.source==="string"&&r.source.length<=300&&
  ["relevant","not_relevant","uncertain"].includes(r.relevance)&&["reported","denied","uncertain"].includes(r.stance)))throw Error("Invalid analysis reports");
 return {...v,reports:v.reports.map(r=>({...r,headline:typeof r.headline==="string"?r.headline.slice(0,500):r.text.slice(0,500)}))};
}

function videoResult(value:unknown):Video {
 const v=value as Video;
 if(!v||typeof v!=="object"||typeof v.status!=="string")throw Error("Invalid video manifest");
 if(v.status!=="available")return {status:v.status==="source_permission_required"?v.status:"unavailable"};
 const duration=v.duration_seconds;
 if(!videoSource(v)||typeof duration!=="number"||!Number.isFinite(duration)||duration<=0||duration>245||
  !Array.isArray(v.sources)||v.sources.length<1||v.sources.length>4||
  !v.sources.every(s=>s&&Number.isSafeInteger(s.id)&&s.id>0&&typeof s.source==="string"))throw Error("Invalid video manifest");
 return v;
}

/** A content-keyed child keeps ordinary polling out of the media lifecycle. */
function CaptionedVideo({video,src,onError,onLoadedMetadata}:{video:Video;src:string;onError:()=>void;onLoadedMetadata:()=>void}){
 const plan=useMemo(()=>parseCaptionPlan(video),[video]);
 const identity=plan?.identity||"";
 const [resource,setResource]=useState<{identity:string;status:"ready"|"unavailable";url?:string;plan?:CaptionPlan;reason?:string}>({identity:"",status:"unavailable"});
 const [showing,setShowing]=useState(true),[trackError,setTrackError]=useState(false),[pausedHint,setPausedHint]=useState(false);
 const media=useRef<HTMLVideoElement|null>(null),track=useRef<HTMLTrackElement|null>(null),wanted=useRef(true),ownedResource=useRef("");
 useEffect(()=>{
  if(!plan)return;
  let cancelled=false,ownedUrl="";
  void prepareBriefingCaptions(plan).then(result=>{
   if(cancelled)return;
   if(result.status!=="ready"){setResource({identity,status:"unavailable",reason:result.reason});return;}
   try{
    ownedUrl=URL.createObjectURL(new Blob([result.vtt],{type:"text/vtt;charset=utf-8"}));
    ownedResource.current=ownedUrl;setResource({identity,status:"ready",url:ownedUrl,plan:result.plan});
   }catch{setResource({identity,status:"unavailable",reason:"browser"});}
  });
  return()=>{cancelled=true;if(ownedUrl){if(ownedResource.current===ownedUrl)ownedResource.current="";URL.revokeObjectURL(ownedUrl);}};
  // Identity includes every consumed text, timing, digest and artifact field,
  // but excludes polling clocks. A fresh equivalent JSON object changes none.
 },[identity]);
 const ready=!!identity&&resource.identity===identity&&resource.status==="ready"&&!!resource.url&&ownedResource.current===resource.url;
 const url=ready?resource.url:undefined;
 useEffect(()=>{
  setTrackError(false);
  if(!url)return;
  const element=track.current,tracks=media.current?.textTracks;
  const initialise=()=>{if(element?.track){element.track.mode=wanted.current?"showing":"disabled";setShowing(wanted.current);}};
  const sync=()=>{if(element?.track){const enabled=element.track.mode==="showing",changed=enabled!==wanted.current;wanted.current=enabled;setShowing(enabled);if(!enabled)setPausedHint(false);else if(changed)setPausedHint(!!media.current?.paused);}};
  const failed=(event:Event)=>{event.stopPropagation();setTrackError(true);};
  initialise();element?.addEventListener("load",initialise);element?.addEventListener("error",failed);tracks?.addEventListener?.("change",sync);
  return()=>{element?.removeEventListener("load",initialise);element?.removeEventListener("error",failed);tracks?.removeEventListener?.("change",sync);};
 },[url]);
 const toggle=()=>{const enabled=!showing;wanted.current=enabled;if(track.current?.track)track.current.track.mode=enabled?"showing":"disabled";setShowing(enabled);setPausedHint(enabled&&!!media.current?.paused);};
 return <>
  <video ref={media} controls playsInline preload="metadata" style={{width:"100%",maxHeight:"55vh",background:"#050c12",borderRadius:5}} src={src} onError={event=>{if(event.target===event.currentTarget)onError();}} onLoadedMetadata={onLoadedMetadata} onPlaying={()=>setPausedHint(false)} aria-label="Narrated attributed source briefing">
   {url?<track key={identity} ref={track} kind="captions" srcLang="en" label="Source narration (segment timing)" src={url} default/>:null}
  </video>
  {ready?<>
   <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}><button style={button} onClick={toggle} disabled={trackError} aria-pressed={showing}>{showing?"Hide captions":"Show captions"}</button><span>Captions follow source-card audio segments; they are not word aligned.</span></div>
   {pausedHint&&!trackError?<p role="status" style={{margin:0,fontSize:12,color:"#9db5bb"}}>If captions do not appear while paused, resume playback to show them.</p>:null}
   {trackError?<p role="status">The caption track could not be loaded. The narration transcript remains available below.</p>:null}
   <details><summary style={{cursor:"pointer",minHeight:44}}>Narration transcript</summary><div role="region" aria-label="Complete narration transcript" tabIndex={0} style={{maxHeight:"min(40vh,22rem)",overflowY:"auto",overflowWrap:"anywhere"}}><ol>{resource.plan?.segments.map((segment,index)=><li key={index}><p style={{whiteSpace:"pre-wrap"}}>{segment.text}</p></li>)}</ol></div></details>
  </>:<p role="status">{identity&&resource.identity!==identity?"Checking captions and transcript…":resource.identity===identity&&resource.reason==="crypto"?"Captions and transcript unavailable: this browser cannot verify caption metadata.":"Captions and transcript unavailable for this video."}</p>}
 </>;
}

/** Free operator-triggered work; viewing never starts a model or media process. */
export function LocalBriefingPanel({eventIds=[],operatorKey="",onConfigureOperator,mode="all"}:Props){
 const [status,setStatus]=useState<Status|null>(null),[analysis,setAnalysis]=useState<Analysis|null>(null),[video,setVideo]=useState<Video|null>(null);
 const [error,setError]=useState(""),[action,setAction]=useState(""),[pending,setPending]=useState<Job|null>(null);
 const [mediaError,setMediaError]=useState(false);
 const refreshRef=useRef<(()=>Promise<void>)|null>(null),actionController=useRef<AbortController|null>(null),activeRef=useRef(false);
 const ids=[...new Set(eventIds)];const validIds=ids.every(id=>Number.isSafeInteger(id)&&id>0);
 useEffect(()=>{
  activeRef.current=true;
  if(SHOWCASE)return()=>{activeRef.current=false;};
  let stopped=false,timer:ReturnType<typeof setTimeout>|undefined,inFlight=false;
  const controller=new AbortController();
  const read=async(path:string)=>{const r=await apiFetch(`${API_BASE}/briefing/${path}`,{signal:controller.signal});if(r.status===403){const d=await r.json().catch(()=>null);if(d?.detail?.code==="SourcePermissionRequired")return {status:"source_permission_required",reports:[]};}if(!r.ok)throw Error(`Local tools unavailable (HTTP ${r.status})`);return r.json();};
  const refresh=async()=>{
   if(stopped||inFlight)return;inFlight=true;clearTimeout(timer);
   let delay=15000;
   try{
    const [s,a,v]=await Promise.all([read("status"),...(mode!=="video"?[read("latest")]:[Promise.resolve(null)]),...(mode!=="analysis"?[read("video/manifest")]:[Promise.resolve(null)])]);
    if(stopped)return;
    if(!s?.local_ai||!s?.video||typeof s.local_ai.enabled!=="boolean"||typeof s.video.enabled!=="boolean")throw Error("Invalid local tools status");
    const next=a?analysisResult(a):null;
    const nextVideo=v?videoResult(v):null;
    setStatus(s);setAnalysis(next);setVideo(nextVideo);setError("");
    if(s.local_ai.state==="running"||s.video.state==="running")delay=2000;
   }catch(e){if(!stopped)setError(e instanceof Error?e.message:"Local tools unavailable");}
   finally{inFlight=false;if(!stopped)timer=setTimeout(()=>void refresh(),delay);}
  };
  refreshRef.current=refresh;void refresh();
  return()=>{stopped=true;activeRef.current=false;refreshRef.current=null;controller.abort();actionController.current?.abort();clearTimeout(timer);};
 },[mode]);

 const run=async(kind:Job)=>{
  const limit=kind==="video"?4:8;
  if(SHOWCASE||pending||!validIds||ids.length>limit)return;
  if(!operatorKey.trim()){onConfigureOperator?.();return;}
  const controller=new AbortController();actionController.current=controller;setPending(kind);setAction("");
  try{
   const r=await apiFetch(`${API_BASE}/briefing/${kind}`,{method:"POST",headers:{"Content-Type":"application/json","X-Admin-Key":operatorKey},body:JSON.stringify({event_ids:ids}),signal:controller.signal});
   if(!activeRef.current||controller.signal.aborted)return;
   if(r.status!==202){setAction(r.status===401||r.status===403?"Operator access was rejected":r.status===409?"A local job is already running":`Request failed (HTTP ${r.status})`);return;}
   setStatus(previous=>previous?{...previous,[kind==="analyze"?"local_ai":"video"]:{...(kind==="analyze"?previous.local_ai:previous.video),state:"running"}}:previous);
   setAction(kind==="video"?"Video queued locally. The last completed video remains available until validation finishes.":"Analysis queued locally. Only validated source excerpts and labels will be displayed.");
   await refreshRef.current?.();
  }catch{if(activeRef.current&&!controller.signal.aborted)setAction("Local request failed; it was not retried automatically");}
  finally{if(actionController.current===controller)actionController.current=null;if(activeRef.current)setPending(null);}
 };

 const controls=(kind:Job)=>{
  const videoJob=kind==="video",state=videoJob?status?.video:status?.local_ai,limit=videoJob?4:8;
  const over=ids.length>limit||!validIds,busy=pending!==null||state?.state==="running";
  return <div style={{display:"flex",gap:8,alignItems:"center",flexWrap:"wrap"}}>
   <button style={button} disabled={SHOWCASE||!state?.enabled||busy||over} onClick={()=>void run(kind)}>{pending===kind?"Sending…":videoJob?"Make narrated briefing":"Analyze source reports"}</button>
   <span style={{fontSize:12,color:over?"#f5bb7b":"#9db5bb"}}>{over?`Choose at most ${limit} valid reports`:ids.length?`${ids.length} selected ${ids.length===1?"report":"reports"}`:`Latest eligible reports · up to ${videoJob?3:4}`}</span>
  </div>;
 };
 const src=video?videoSource(video):"";
 return <section className="local-briefing-panel" aria-label="Free local briefing tools" style={{display:"grid",gap:12,fontSize:13,lineHeight:1.55,color:"#c2d5da",minWidth:0}}>
  {SHOWCASE?<p role="status">Local tools are disconnected in the synthetic showcase. No model or video process is started.</p>:null}
  <p style={{margin:0,color:"#a9c4cd"}}>Source eligibility: Telegram reports and t.me/telegram.me citations are excluded from local AI and synthesized narration because this deployment has no recorded context-specific creator consent. Automatic selection skips them; an explicit selection containing one is rejected in full. Other source rights still need review for the intended use. Viewing reports and source digests does not start AI.</p>
  {error?<p role="status" style={{color:"#f5bb7b",margin:0}}>{error}. Last completed results may be shown below.</p>:null}
  {mode!=="video"?<article style={box}>
   <h3 style={{margin:"0 0 5px",fontSize:17,color:"#b3eee2"}}>Local source triage</h3>
   <p role="status" style={{margin:"0 0 10px",color:"#9db5bb"}}>{analysis?.status==="source_permission_required"?"Artifact withheld · source permission required":stateText(status?.local_ai)}{status?.local_ai.model?` · ${status.local_ai.model}`:""}</p>
   <p>AI labels topics, wording and exact source mentions. It does not verify claims, assign coordinates or estimate severity.</p>
   {controls("analyze")}
   {!operatorKey&&status?.local_ai.enabled?<p>Operator access is required to start a local job. <button style={button} onClick={onConfigureOperator}>Configure access</button></p>:null}
   {analysis?.status==="source_permission_required"?<p role="status">Source permission required · this analysis is withheld pending eligibility review. The stored file was preserved.</p>:null}
   {analysis?.status==="available"?<>
    <p>{analysis.stale?<strong style={{color:"#f5bb7b"}}>STALE RESULT · </strong>:null}Generated {date(analysis.generated_at)}. Publisher text is preserved; model labels remain unreviewed.</p>
    {analysis.reports.map(r=><div key={r.id} style={{borderTop:"1px solid #29404b",padding:"12px 0",overflowWrap:"anywhere"}}>
     <strong>[src:{r.id}] {r.source}</strong><div title="Publication, update or sensor acquisition, depending on the source" style={{fontSize:12,color:"#9db5bb"}}>Source time {date(r.published_at)}</div>
     <p style={{whiteSpace:"pre-wrap"}}>{r.headline||r.text}</p>
     <div>Topic: {r.relevance.replace(/_/g," ")} · Linguistic stance: {r.stance}</div>
     {([['place_mentions','Places mentioned'],['actor_mentions','Actors mentioned'],['quantity_mentions','Quantities quoted']] as const).map(([key,label])=>{
      const values=Array.isArray(r.mentions?.[key])?r.mentions[key].filter(m=>typeof m?.text==="string"&&m.text.length<=160).slice(0,6):[];
      return values.length?<div key={key}><span style={{color:"#9db5bb"}}>{label}: </span>{values.map(m=>m.text).join(" · ")}{key==="place_mentions"?" (not verified incident locations)":""}</div>:null;
     })}
     <details><summary style={{cursor:"pointer",minHeight:32}}>Source excerpt and reference</summary><p style={{whiteSpace:"pre-wrap"}}>{r.text}</p>{r.text_truncated?<p>Excerpt truncated; original source hash is retained in provenance.</p>:null}{sourceUrl(r.source_url)?<a href={sourceUrl(r.source_url)} target="_blank" rel="noopener noreferrer">Open publisher source ↗</a>:<span>Source link unavailable</span>}</details>
    </div>)}
    <details><summary>Processing provenance</summary><p>Model: {analysis.provenance?.model||"Unavailable"}</p><p style={{overflowWrap:"anywhere"}}>Model digest: {analysis.provenance?.model_digest||"Unavailable"}</p><p>{analysis.semantic_entailment||"Semantic and factual support remain unreviewed."}</p></details>
   </>:<p>No validated local result yet. Viewing this panel does not start analysis.</p>}
  </article>:null}
  {mode!=="analysis"?<article style={box}>
   <h3 style={{margin:"0 0 5px",fontSize:17,color:"#b3eee2"}}>Narrated source briefing</h3>
   <p role="status" style={{margin:"0 0 10px",color:"#9db5bb"}}>{video?.status==="source_permission_required"?"Artifact withheld · source permission required":stateText(status?.video)}</p>
   <p>Local synthetic speech and editorial source cards. This is a reading of attributed reports, with no incident footage or invented visual evidence.</p>
   {controls("video")}
   {video?.status==="source_permission_required"?<p role="status">Source permission required · this narrated video is withheld pending eligibility review. The stored file was preserved.</p>:null}
   {src?<>
    <p>{video?.stale?<strong style={{color:"#f5bb7b"}}>STALE VIDEO · </strong>:null}Generated {date(video?.generated_at)}{typeof video?.duration_seconds==="number"?` · ${Math.round(video.duration_seconds)} seconds`:""}</p>
    <CaptionedVideo key={src} video={video!} src={src} onError={()=>setMediaError(true)} onLoadedMetadata={()=>setMediaError(false)}/>
    {mediaError?<p role="status">The completed video could not be played. Refresh the artifact or check provider health; no substitute video was loaded.</p>:null}
    <details><summary>Video source references</summary>{video?.sources?.slice(0,4).map(s=><p key={s.id}>[src:{s.id}] {s.source} · {date(s.published_at)} {sourceUrl(s.source_url)?<a href={sourceUrl(s.source_url)} target="_blank" rel="noopener noreferrer">Publisher source ↗</a>:null}</p>)}<p style={{overflowWrap:"anywhere"}}>SHA-256: {video?.sha256||"Unavailable"}</p></details>
   </>:<p>No validated narrated video yet. A failed render never substitutes a demonstration or an incomplete file.</p>}
  </article>:null}
  {action?<p role="status" style={{margin:0,color:"#c9f2e9"}}>{action}</p>:null}
 </section>;
}
