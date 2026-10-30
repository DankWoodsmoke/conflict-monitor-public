import { useEffect, useRef, useState } from "react";
import type { ViewMode } from "../App";
import { showcase } from "../lib/showcase";

const chapters: Array<{view:ViewMode;name:string;title:string;body:string;features:string[]}> = [
  {view:"earth",name:"Earth workspace",title:"Follow a position back to its source.",body:"One Earth workspace combines reports, tracking, search, layers and replay. Unknown coordinates stay in the feed. Aircraft are surface projections and inherited infrastructure is optional and unverified.",features:["Source filters + searchable report feed","Observation clocks + surface projections","Thermal observations + source links","Persistent Earth with Media and Brief panels"]},
  {view:"media",name:"Media desk",title:"Keep observation separate from interpretation.",body:"A four-panel media desk brings broadcast, briefing, analysis and camera sources together. The exercise panels are explicitly illustrative; no third-party streams are loaded.",features:["Four media panels","Breaking + source intelligence","Event-type matrix","Radiation provider panel"]},
  {view:"sitrep",name:"Situation report",title:"Make the reasoning inspectable.",body:"Open the intelligence brief, compare source events and inspect competing hypotheses. Analysis, assumptions and missing evidence remain visible alongside the assessment.",features:["Situation + escalation assessment","Economic + humanitarian context","Hypotheses + falsifying observations","Source references + report history"]},
];

export function ShowcaseBar({view,onView}:{view:ViewMode;onView:(v:ViewMode)=>void}) {
  const [open,setOpen]=useState(false);
  const tourRef=useRef<HTMLElement>(null);
  const index=Math.max(0,chapters.findIndex(c=>c.view===view));
  const chapter=chapters[index];
  useEffect(()=>{
    if(!open)return;
    const prior=document.activeElement as HTMLElement|null;
    tourRef.current?.querySelector<HTMLButtonElement>('.tour-close')?.focus();
    const handler=(event:KeyboardEvent)=>{
      const foregroundModal=[...document.querySelectorAll('[role="dialog"][aria-modal="true"]')].some(node=>node.getClientRects().length>0);
      if(event.key==='Escape'&&!event.defaultPrevented&&!foregroundModal){event.preventDefault();event.stopImmediatePropagation();setOpen(false);}
    };
    window.addEventListener('keydown',handler,true);
    return()=>{window.removeEventListener('keydown',handler,true);if(prior?.isConnected)prior.focus();};
  },[open]);
  const download=()=>{
    const blob=new Blob([JSON.stringify({schema:"conflict-monitor-showcase/1",mode:"synthetic",...showcase},null,2)],{type:"application/json"});
    const url=URL.createObjectURL(blob); const a=document.createElement("a");a.href=url;a.download="conflict-monitor-synthetic-exercise.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),0);
  };
  return <>
    <div className="showcase-banner" role="region" aria-label="Synthetic showcase controls">
      <div className="showcase-wordmark"><span className="showcase-dot"/>SHOWCASE<span className="showcase-divider">/</span><span className="showcase-disclosure">Synthetic exercise · no live intelligence</span></div>
      <div className="showcase-actions"><a className="live-earth-link" href="?view=earth">Open live Earth ↗</a><button onClick={()=>setOpen(v=>!v)} aria-expanded={open} aria-controls="capability-tour">Capability tour <span>↗</span></button><button onClick={download} title="Export the exact synthetic fixture and reference clock">Export exercise ↓</button></div>
    </div>
    {open && <section id="capability-tour" ref={tourRef} className="showcase-tour" role="dialog" aria-modal="false" aria-label="Capability tour">
      <button className="tour-close" onClick={()=>setOpen(false)} aria-label="Close capability tour">×</button>
      <span className="tour-kicker">CONFLICT MONITOR / CAPABILITY TOUR</span>
      <nav className="tour-chapters" aria-label="Tour chapters">{chapters.map((c,i)=><button key={c.view} onClick={()=>onView(c.view)} aria-current={view===c.view?"step":undefined}><span>0{i+1}</span>{c.name}</button>)}</nav>
      <h1>{chapter.title}</h1><p>{chapter.body}</p>
      <ul>{chapter.features.map(f=><li key={f}>{f}</li>)}</ul>
      <footer><span>{index+1} of {chapters.length}</span><button onClick={()=>onView(chapters[(index+1)%chapters.length].view)}>Next capability →</button></footer>
    </section>}
  </>;
}
