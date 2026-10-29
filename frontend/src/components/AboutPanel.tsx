import { useEffect, useRef, useState } from "react";
import { SHOWCASE } from "../lib/runtime";

const STORAGE_KEY="cm_seen_methods_v2";
const tabs=["Overview","Evidence & sources","Deployment"] as const;
export function AboutPanel({onClose}:{onClose:()=>void}) {
  const [tab,setTab]=useState<typeof tabs[number]>("Overview");
  const dialog=useRef<HTMLDivElement>(null);
  const close=()=>{try{localStorage.setItem(STORAGE_KEY,"1");}catch{}onClose();};
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null;
    dialog.current?.focus();
    const handler=(e:KeyboardEvent)=>{
      if(e.key==="Escape")close();
      if(e.key==="Tab"){
        const nodes=dialog.current?.querySelectorAll<HTMLElement>('button,a[href],[tabindex="0"]');
        if(!nodes?.length)return;
        const first=nodes[0],last=nodes[nodes.length-1];
        if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
        else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
      }
    };
    window.addEventListener("keydown",handler);
    return()=>{window.removeEventListener("keydown",handler);previous?.focus();};
  },[]);
  return <div className="methods-backdrop" onClick={e=>{if(e.target===e.currentTarget)close();}}>
    <div className="methods-dialog" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="methods-title" tabIndex={-1}>
      <header role="presentation"><span className="tour-kicker">CONFLICT MONITOR / RELEASE CANDIDATE</span><button onClick={close} aria-label="Close about and methodology">×</button><h1 id="methods-title">Evidence in context.</h1><p>Reports, spatial context, media and situation analysis in one inspectable workspace.</p></header>
      <nav aria-label="About sections">{tabs.map(t=><button key={t} onClick={()=>setTab(t)} aria-pressed={tab===t}>{t}</button>)}</nav>
      <div className="methods-body">
        {tab==="Overview"&&<><h2>One Earth workspace</h2><div className="methods-grid">{[
          ["01 / Earth","Search reports and tracks, inspect original sources, choose spatial layers and replay recorded snapshots on one persistent Earth. Unknown locations stay unresolved; track heights are not invented."],
          ["02 / Media","Open media beside Earth. External broadcasts load only when selected; publisher commentary remains separate from observed evidence."],
          ["03 / Brief","Read free attributed source digests with original report references and unassessed risk. Optional model analysis adds hypotheses and context; generated analysis remains unreviewed."],
        ].map(([title,text])=><article key={title}><h3>{title}</h3><p>{text}</p></article>)}</div><h2>Choose a mode deliberately</h2><p>{SHOWCASE?"You are viewing a synthetic exercise. All incidents, tracks, market prices and analysis fixtures are fabricated for demonstrating the interface. Data providers and model calls stay offline. Google imagery is available only if explicitly enabled in Settings.":"Operational mode uses your configured backend. Collection and model generation are disabled by default. A connected transport does not certify source freshness or factual accuracy."}</p><a className="methods-link" href="?showcase=true">Explore the synthetic capability showcase ↗</a></>}
        {tab==="Evidence & sources"&&<><h2>Same standard for every source</h2><p>A publisher's identity, affiliation or political perspective cannot establish whether a claim is true. Preserve the raw observation, attributed claim, timestamp, source link and subsequent corrections. Keep analysis distinguishable from its evidence.</p><ul><li><strong>Multiple reports</strong> counts recorded sources. Independence remains unassessed until their original evidence and transmission lineage are examined.</li><li><strong>Source ratings</strong> are curated legacy metadata. They are not calibrated probabilities, current audits or claim verification.</li><li><strong>Location precision</strong> describes the method or geographic level. No uncertainty radius is inferred from a publisher score.</li><li><strong>Thermal observations</strong> may reflect industrial activity, vegetation fires or other causes. Proximity to a report does not prove a strike or justify moving its coordinates.</li><li><strong>Navigation anomalies</strong> are low-quality position signals. These alone do not establish intentional interference.</li><li><strong>Report-activity indices</strong> summarize configured heuristics. They are not probabilities of escalation or a verified threat assessment.</li><li><strong>Model output</strong> is extracted or generated analysis. Preserve failures and missing evidence rather than substituting authoritative-looking fallback claims.</li></ul><h2>Sources and coverage</h2><p>Optional connectors include Telegram, configured RSS publishers, ADS-B, AIS, orbital elements, NASA FIRMS and market feeds. Availability, coverage, latency, terms and source permissions vary. Absence of a report is not evidence that nothing happened.</p><p>Original reports remain inspectable from the feed's Evidence & provenance control. A disagreement should be recorded and investigated, not erased by an average, a majority or a higher source score.</p></>}
        {tab==="Deployment"&&<><h2>Explicit connections, inspectable operation</h2><p>The public distribution ships without credentials, Telegram sessions, collected private data or the historical server backup. Configure providers server-side and enable collection deliberately. Run the provided release checks before deployment.</p><p>Media links and data-provider products remain subject to their owners' terms. The application license does not grant rights to redistribute third-party imagery, broadcasts or collected datasets.</p><h2>Verification limits</h2><p>The synthetic showcase verifies interface behavior and can be exported with its reference clock. It cannot certify live provider coverage, model accuracy, historical completeness or real-world event truth. Those require separate source-backed evaluations.</p><p>Public provenance and installation details live in the repository documentation. Local operational secrets belong in environment configuration, never in a browser bundle or a release archive.</p></>}
      </div>
      <footer><span>{SHOWCASE?"SYNTHETIC EXERCISE":"OPERATIONAL CONFIGURATION"}</span><button onClick={close}>Open workspace →</button></footer>
    </div>
  </div>;
}
export function shouldShowAbout(){try{return localStorage.getItem(STORAGE_KEY)!=="1";}catch{return true;}}
