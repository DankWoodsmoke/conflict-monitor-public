import { useEffect, useId, useState } from "react";
import { SHOWCASE, safeUrl } from "../lib/runtime";

/** External streams contact providers only after explicit viewer activation. */
export function MediaFrame(props: React.IframeHTMLAttributes<HTMLIFrameElement>) {
  const [enabled,setEnabled]=useState(false),[frameState,setFrameState]=useState("Provider not contacted");
  const id=useId().replace(/:/g,"");
  useEffect(()=>{if(!enabled)return;setFrameState("Connecting to external provider…");const timer=setTimeout(()=>setFrameState(current=>current.startsWith("Connecting")?"Provider response unavailable or blocked · open source directly":current),15000);return()=>clearTimeout(timer);},[enabled,props.src]);
  if (!SHOWCASE && enabled) return <div className="external-media-frame"><iframe {...props} src={safeUrl(props.src)} referrerPolicy="strict-origin-when-cross-origin" onLoad={event=>{setFrameState("External frame received · playback and live status unverified");props.onLoad?.(event);}} onError={event=>{setFrameState("Provider could not be loaded · open source directly");props.onError?.(event);}}/><div className="external-media-status" role="status">{frameState}<a href={safeUrl(props.src)} target="_blank" rel="noopener noreferrer">Open source ↗</a><button onClick={()=>setEnabled(false)} aria-label="Disconnect external media">×</button></div></div>;
  return <div className="media-preview">
    <svg viewBox="0 0 400 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs><pattern id={`media-grid-${id}`} width="25" height="25" patternUnits="userSpaceOnUse"><path d="M25 0H0V25" fill="none" stroke="#17374a" strokeWidth=".5"/></pattern></defs>
      <rect width="400" height="200" fill="#07111b"/><rect width="400" height="200" fill={`url(#media-grid-${id})`}/>
      <path d="M0 160L38 140L60 154L95 116L133 124L165 91L205 109L235 68L275 80L317 42L355 57L400 20" fill="none" stroke="#49c4c4" strokeWidth="1.5" opacity=".6"/>
      <circle cx="235" cy="68" r="24" fill="none" stroke="#49c4c4" opacity=".3"/><circle cx="235" cy="68" r="4" fill="#64e7d9"/>
      <path d="M0 182H400" stroke="#23495a"/>
    </svg>
    <div className="media-preview-caption"><span>{SHOWCASE?"SYNTHETIC EXERCISE":"EXTERNAL SOURCE"}</span><strong>{props.title || "Media source"}</strong>
      {SHOWCASE?<p>Provider disconnected · illustrative preview</p>:<button onClick={()=>setEnabled(true)}>Load external media ↗</button>}
    </div>
  </div>;
}

export function ShowcaseBriefing() {
  const [playing,setPlaying]=useState(false);
  return <div className="showcase-briefing" role="region" aria-label="Synthetic briefing exercise" tabIndex={0}><span className="tour-kicker">SYNTHETIC BRIEFING / TEXT EXERCISE</span><h2>Signals. Sources.<br/>Open questions.</h2><p>Multiple reports can share one origin. A thermal observation does not establish a strike. Show the evidence and preserve uncertainty.</p><div className={playing?"briefing-wave playing":"briefing-wave"} aria-hidden="true">{Array.from({length:32},(_,i)=><i key={i} style={{height:8+((i*17)%33),animationDelay:`${i*.04}s`}}/>)}</div><button onClick={()=>setPlaying(v=>!v)} aria-pressed={playing}>{playing?"Pause visual demonstration":"Play visual demonstration"}</button><small>Illustration only · no recorded footage or narration</small></div>;
}
