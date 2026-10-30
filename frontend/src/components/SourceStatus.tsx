import {useEffect,useRef,useState} from "react";
import {apiFetch} from "../lib/api";
import {API_BASE} from "../lib/runtime";

type Feed={source:string;status:string;cache_age_seconds:number|null;publication_age_seconds:number|null;publication_stale:boolean;published_items:number;error_type:string|null};
type TelegramStatus={enabled:boolean;status:string;mode?:string;cache_age_seconds:number|null;publication_age_seconds:number|null;publication_stale?:boolean;startup_limit_per_channel?:number;coverage_limitation?:string;channels:Record<string,{status:string;processed:number;history_complete:boolean;startup_or_cycle_limit?:number;last_check_at?:string}>};
type Status={mode?:string;telegram?:TelegramStatus;news_feeds?:{mode:string;enabled:boolean;feeds:Feed[]};rss?:{mode:string;enabled:boolean;feeds:Feed[]};aircraft?:Record<string,unknown>;maritime?:Record<string,unknown>;satellites?:Record<string,unknown>;thermal_observations?:Record<string,unknown>};
export function ageLabel(seconds:unknown):string{
 if(typeof seconds!=="number"||!Number.isFinite(seconds)||seconds<0)return "Unknown";
 if(seconds<60)return `${Math.floor(seconds)}s`;
 if(seconds<3600)return `${Math.floor(seconds/60)}m`;
 if(seconds<86400)return `${Math.floor(seconds/3600)}h`;
 return `${Math.floor(seconds/86400)}d`;
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
   <h2>RSS reports</h2>{feeds.length?<div className="source-health-list">{feeds.map(feed=><article key={feed.source}><strong>{feed.source.replace(/_/g," ")}</strong><span>{feed.status}</span><dl><dt>Fetch age</dt><dd>{ageLabel(feed.cache_age_seconds)}</dd><dt>Newest source time age</dt><dd>{ageLabel(feed.publication_age_seconds)}{feed.publication_stale?" · old source time":""}</dd><dt>Reports retained in last poll</dt><dd>{feed.published_items??"Unknown"}</dd></dl>{feed.error_type&&<p>Provider result: {feed.error_type}</p>}</article>)}</div>:<p>No RSS provider receipts are available.</p>}
   <h2>Telegram reports</h2>{data?.telegram?<div className="source-health-list"><article><strong>Telegram collection</strong><span>{data.telegram.status}</span><dl><dt>Fetch age</dt><dd>{ageLabel(data.telegram.cache_age_seconds)}</dd><dt>Newest source publication age</dt><dd>{ageLabel(data.telegram.publication_age_seconds)}{data.telegram.publication_stale?" · old publication":""}</dd><dt>Startup limit per channel</dt><dd>{data.telegram.startup_limit_per_channel??"Unknown"}</dd></dl><p>{data.telegram.coverage_limitation||"Selected channels only; source publication time is not incident time."}</p></article>{Object.entries(data.telegram.channels||{}).map(([name,channel])=><article key={name}><strong>@{name}</strong><span>{channel.status}</span><dl><dt>Processed in last check</dt><dd>{channel.processed??"Unknown"}</dd><dt>History coverage</dt><dd>{channel.history_complete===true?"Declared complete":"Incomplete / bounded"}</dd><dt>Check limit</dt><dd>{channel.startup_or_cycle_limit??"Unknown"}</dd></dl></article>)}</div>:<p>No Telegram provider receipts are available.</p>}
   <h2>Tracking providers</h2>{([['Aircraft',data?.aircraft],['Vessels',data?.maritime],['Orbits',data?.satellites],['Thermal observations',data?.thermal_observations]] as const).map(([label,provider])=><article className="tracking-status-row" key={label}><strong>{label}</strong><span>{String(provider?.status||"unavailable")}</span><small>{String(provider?.source||"")}</small></article>)}
   {coverage&&<><h2>Aircraft receiver coverage</h2><p>{coverage.kind==="regional_circles"?`${coverage.circles?.length??0} selected regional circles · ${coverage.radius_nm??"Unknown"} nautical-mile radius. One request per ${coverage.minimum_request_interval_seconds??"Unknown"} seconds; nominal regional revisit ${coverage.nominal_revisit_seconds??"Unknown"} seconds plus network time.`:"Selected regional receiver coverage; global coverage is not provided."}</p>{regions.length>0&&<div className="source-health-list">{regions.map(region=><article key={region.id}><strong>{region.label||region.id}</strong><span>{region.status}</span><dl><dt>Fetch age</dt><dd>{ageLabel(region.cache_age_seconds)}</dd></dl></article>)}</div>}<p>Reported positions expire by their own observation clocks. Receiver silence and areas outside these circles do not establish absence.</p></>}
   <p>Empty coverage does not prove absence. Aircraft identity and a cause for navigation anomalies require separate evidence. Aircraft in Earth are surface projections, not surveyed 3D heights. Orbital markers have been removed from this workspace.</p>
  </div><footer><span>Mode: {data?.mode||"Unknown"}</span><button onClick={()=>setRefresh(v=>v+1)}>Refresh status</button></footer>
 </section></div>}</>;
}
