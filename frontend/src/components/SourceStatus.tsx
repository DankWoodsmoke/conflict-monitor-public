import {useEffect,useRef,useState} from "react";
import {apiFetch} from "../lib/api";
import {API_BASE} from "../lib/runtime";
import {BUILD_ID} from "../lib/build";

type Feed={source:string;status:string;cache_age_seconds:number|null;publication_age_seconds:number|null;publication_stale:boolean;published_items:number;error_type:string|null};
type TelegramStatus={
 enabled:boolean;status:string;transport?:"disabled"|"bot"|"session";mode?:string;
 cache_age_seconds:number|null;publication_age_seconds:number|null;publication_stale?:boolean;
 startup_limit_per_channel?:number;retention_hours?:number;retry_delay_seconds?:number;
 coverage_limitation?:string;
 channels:Record<string,{status:string;processed:number;history_complete:boolean;startup_or_cycle_limit?:number;last_check_at?:string}>;
};
type ClassificationStatus={rss_classification?:string;telegram_classification?:string;local_ai_scope?:string;rubric_version?:string;semantic_quality?:string;verified_critical_alerts_enabled?:boolean};
type Status={public_read_only?:boolean;public_reports_enabled?:boolean;public_observations_enabled?:boolean;public_aircraft_enabled?:boolean;public_tracking_enabled?:boolean;public_notice?:string;public_tracking_unavailable_reason?:string;mode?:string;classification?:ClassificationStatus;telegram?:TelegramStatus;news_feeds?:{mode:string;enabled:boolean;feeds:Feed[]};rss?:{mode:string;enabled:boolean;feeds:Feed[]};aircraft?:Record<string,unknown>;maritime?:Record<string,unknown>;satellites?:Record<string,unknown>;thermal_observations?:Record<string,unknown>};
export function ageLabel(seconds:unknown):string{
 if(typeof seconds!=="number"||!Number.isFinite(seconds)||seconds<0)return "Unknown";
 if(seconds<60)return `${Math.floor(seconds)}s`;
 if(seconds<3600)return `${Math.floor(seconds/60)}m`;
 if(seconds<86400)return `${Math.floor(seconds/3600)}h`;
 return `${Math.floor(seconds/86400)}d`;
}
function TelegramCoverage({status}:{status:TelegramStatus}){
 const bot=status.transport==="bot";
 const transport=bot?"Publisher-authorized bot":status.transport==="session"?"Legacy account session":status.transport==="disabled"?"Disabled":"Unspecified";
 return <div className="source-health-list">
  <article><strong>Telegram collection</strong><span>{status.status}</span>
   <dl><dt>Transport</dt><dd>{transport}</dd>
    <dt>Fetch age</dt><dd>{ageLabel(status.cache_age_seconds)}</dd>
    <dt>Newest source publication age</dt><dd>{ageLabel(status.publication_age_seconds)}{status.publication_stale?" · old publication":""}</dd>
    {bot&&typeof status.retention_hours==="number"&&<><dt>Provider update retention</dt><dd>Up to {status.retention_hours} hours</dd></>}
    {!bot&&status.enabled&&<><dt>Startup limit per channel</dt><dd>{status.startup_limit_per_channel??"Unknown"}</dd></>}
    {typeof status.retry_delay_seconds==="number"&&status.retry_delay_seconds>0&&<><dt>Reconnect delay</dt><dd>{status.retry_delay_seconds} seconds</dd></>}
   </dl>
   <p>{status.coverage_limitation||"Selected channels only. Source publication time is separate from incident time."}</p>
  </article>
  {Object.entries(status.channels||{}).map(([name,channel])=><article key={name}>
   <strong>@{name}</strong><span>{channel.status}</span>
   <dl><dt>Processed in last check</dt><dd>{channel.processed??"Unknown"}</dd>
    <dt>History coverage</dt><dd>{channel.history_complete===true?"Declared complete":"Incomplete / bounded"}</dd>
    {!bot&&<><dt>Check limit</dt><dd>{channel.startup_or_cycle_limit??"Unknown"}</dd></>}
   </dl>
  </article>)}
 </div>;
}
export function SourceStatus({fallback}:{fallback:string}){
 const [data,setData]=useState<Status|null>(null),[failed,setFailed]=useState(false),[open,setOpen]=useState(false),[refresh,setRefresh]=useState(0);
 const dialog=useRef<HTMLElement>(null);
 useEffect(()=>{
  let cancelled=false,timer:ReturnType<typeof setTimeout>|undefined;const controller=new AbortController();
  const poll=async()=>{
   try{const r=await apiFetch(`${API_BASE}/status`,{signal:controller.signal});if(!r.ok)throw new Error();const d=await r.json();if(!cancelled){setData(d);setFailed(false);}}
   catch{if(!cancelled)setFailed(true);}finally{if(!cancelled)timer=setTimeout(poll,30000);}
  };void poll();return()=>{cancelled=true;controller.abort();clearTimeout(timer);};
 },[refresh]);
 useEffect(()=>{
  if(!open)return;const prior=document.activeElement as HTMLElement|null;dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();
  const key=(e:KeyboardEvent)=>{if(e.key==="Escape")setOpen(false);if(e.key!=="Tab")return;const controls=dialog.current?.querySelectorAll<HTMLButtonElement>("button");if(!controls?.length)return;const first=controls[0],last=controls[controls.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}};
  window.addEventListener("keydown",key);return()=>{window.removeEventListener("keydown",key);prior?.focus();};
 },[open]);
 const news=data?.news_feeds||data?.rss;
 const feeds=Array.isArray(news?.feeds)?news.feeds:[];
 const coverage=data?.aircraft?.coverage as {kind?:string;radius_nm?:number;nominal_revisit_seconds?:number;minimum_request_interval_seconds?:number;circles?:Array<{id:string;label:string;lat:number;lon:number;radius_nm:number}>}|undefined;
 const regions=Array.isArray(data?.aircraft?.regions)?data!.aircraft!.regions as Array<{id:string;label:string;status:string;cache_age_seconds?:number|null}>:[];
 const ok=feeds.filter(f=>f.status==="ok").length;
 const label=failed?"Source status unavailable · last received data may be stale":data?.mode==="collection_disabled"?"Collection disabled":feeds.length?`${news?.mode==="reports"?"Free source reports":"Source collection"} · ${ok}/${feeds.length} feeds received` : fallback;
 return <><span className="source-runtime-label">{label}</span><button className="source-status-button" onClick={()=>setOpen(true)}>Sources &amp; health</button>
 {open&&<div className="methods-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setOpen(false);}}><section ref={dialog} className="methods-dialog source-status-dialog" role="dialog" aria-modal="true" aria-labelledby="source-health-title">
  <header role="presentation"><button onClick={()=>setOpen(false)} aria-label="Close source health">×</button><span className="tour-kicker">PROVIDER OBSERVATIONS</span><h1 id="source-health-title">Sources &amp; health</h1><p>Fetch time and source time are different clocks. RSS source time can represent publication or an update. A successful fetch does not establish the truth or completeness of a report.</p></header>
  <div className="methods-body" role="region" aria-label="Provider status details" tabIndex={0}>{failed&&<p role="status">The current status request failed. Any retained source states below are the last received snapshot.</p>}
   {data?.mode==="public_read_only"?<><h2>Public research scope</h2><p>{data.public_notice}</p><dl><dt>Source reports and history</dt><dd>{data.public_reports_enabled?"Admitted by operator publication review":"Withheld pending publication approval"}</dd><dt>Private tracking and replay</dt><dd>{data.public_tracking_enabled?"Admitted by operator publication review":"Withheld pending publication approval"}</dd><dt>Tracking publication</dt><dd>{data.public_tracking_unavailable_reason||"Public tracking is not available."}</dd><dt>Independent public datasets</dt><dd>{data.public_observations_enabled?"NASA thermal observations · ":""}{data.public_aircraft_enabled?"adsb.lol aircraft snapshots (ODbL)":""} · inspect the Earth source panel for current availability</dd><dt>Generated briefings and media</dt><dd>Not published</dd></dl><p>Publication admission is not an accuracy or completeness claim. Operator credentials, collection diagnostics and generation tools are not exposed by this deployment.</p></>:<><h2>Classification and impact assessment</h2>{data?.classification?<><dl className="assessment-processing"><dt>RSS processing</dt><dd>{(data.classification.rss_classification||"Unknown").replace(/_/g," ")}</dd><dt>Telegram processing</dt><dd>{(data.classification.telegram_classification||"Unknown").replace(/_/g," ")}</dd><dt>Local AI role</dt><dd>{data.classification.local_ai_scope||"Unknown"}</dd><dt>Severity rubric</dt><dd>{data.classification.rubric_version||"Not recorded"}</dd><dt>Semantic quality</dt><dd>{data.classification.semantic_quality||"Unqualified"}</dd><dt>Verified critical alerts</dt><dd>{data.classification.verified_critical_alerts_enabled===false?"Not enabled":"No qualified alert contract"}</dd></dl><p>Not requested means reports are being captured without automatic classification. A configured model is not a measured accuracy result; thermal detections and repeated reports do not establish attack severity.</p></>:<p>Assessment pipeline status unavailable.</p>}
   <h2>RSS reports</h2>{feeds.length?<div className="source-health-list">{feeds.map(feed=><article key={feed.source}><strong>{feed.source.replace(/_/g," ")}</strong><span>{feed.status}</span><dl><dt>Fetch age</dt><dd>{ageLabel(feed.cache_age_seconds)}</dd><dt>Newest source time age</dt><dd>{ageLabel(feed.publication_age_seconds)}{feed.publication_stale?" · old source time":""}</dd><dt>Reports retained in last poll</dt><dd>{feed.published_items??"Unknown"}</dd></dl>{feed.error_type&&<p>Provider result: {feed.error_type}</p>}</article>)}</div>:<p>No RSS provider receipts are available.</p>}
   <h2>Telegram reports</h2>{data?.telegram?<TelegramCoverage status={data.telegram}/>:<p>No Telegram provider receipts are available.</p>}
   <h2>Tracking providers</h2>{([['Aircraft',data?.aircraft],['Vessels',data?.maritime],['Orbits',data?.satellites],['Thermal observations',data?.thermal_observations]] as const).map(([label,provider])=><article className="tracking-status-row" key={label}><strong>{label}</strong><span>{String(provider?.status||"unavailable")}</span><small>{String(provider?.source||"")}</small></article>)}
   {coverage&&<><h2>Aircraft receiver coverage</h2><p>{coverage.kind==="regional_circles"?`${coverage.circles?.length??0} selected regional circles · ${coverage.radius_nm??"Unknown"} nautical-mile radius. One request per ${coverage.minimum_request_interval_seconds??"Unknown"} seconds; nominal regional revisit ${coverage.nominal_revisit_seconds??"Unknown"} seconds plus network time.`:"Selected regional receiver coverage; global coverage is not provided."}</p>{regions.length>0&&<div className="source-health-list">{regions.map(region=><article key={region.id}><strong>{region.label||region.id}</strong><span>{region.status}</span><dl><dt>Fetch age</dt><dd>{ageLabel(region.cache_age_seconds)}</dd></dl></article>)}</div>}<p>Reported positions expire by their own observation clocks. Receiver silence and areas outside these circles do not establish absence.</p></>}
   <p>Empty coverage does not prove absence. Aircraft identity and a cause for navigation anomalies require separate evidence. Aircraft in Earth are surface projections, not surveyed 3D heights. Orbital markers have been removed from this workspace.</p></>}
  </div><footer><span>Mode: {data?.mode||"Unknown"}<small style={{display:"block",marginTop:4}}>UI build {BUILD_ID}</small></span><button onClick={()=>setRefresh(v=>v+1)}>Refresh status</button></footer>
 </section></div>}</>;
}
