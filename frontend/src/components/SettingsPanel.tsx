import { CostChip } from "./Header";
import { useEffect, useRef, useState } from "react";
import { SHOWCASE } from "../lib/runtime";

interface SettingsPanelProps {
  googleKey: string;
  googleEnabled: boolean;
  onApply: (key: string, enabled: boolean) => void;
  onClose: () => void;
  operatorKey?:string;
  onOperatorKeyChange?:(key:string)=>void;
}

export function SettingsPanel({googleKey,googleEnabled,onApply,onClose,operatorKey="",onOperatorKeyChange}:SettingsPanelProps) {
  const [key,setKey]=useState(googleKey);
  const [enabled,setEnabled]=useState(googleEnabled);
  const [operator,setOperator]=useState(operatorKey);
  const ref=useRef<HTMLElement>(null);
  const closeRef=useRef(onClose);closeRef.current=onClose;
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null;
    ref.current?.querySelector<HTMLElement>("button")?.focus();
    const keyboard=(event:KeyboardEvent)=>{
      if(event.key==="Escape")closeRef.current();
      if(event.key!=="Tab")return;
      const controls=Array.from(ref.current?.querySelectorAll<HTMLElement>('button,input,a[href]') || []).filter(e=>!e.hasAttribute("disabled"));
      const first=controls[0],last=controls[controls.length-1];
      if(event.shiftKey && document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first?.focus();}
    };
    window.addEventListener("keydown",keyboard);return()=>{window.removeEventListener("keydown",keyboard);previous?.focus();};
  },[]);
  return <div className="methods-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget)onClose();}}>
    <section className="methods-dialog settings-dialog" ref={ref} role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header role="presentation"><button onClick={onClose} aria-label="Close settings">×</button><span className="tour-kicker">WORKSPACE SETTINGS</span><h1 id="settings-title">Earth &amp; data</h1><p>Choose the imagery behind your reports. Your evidence and source history stay visible across views.</p></header>
      <div className="methods-body">
        <h2>Google Photorealistic 3D Tiles</h2>
        <p>Explore Google’s textured 3D terrain and buildings through Cesium. This is the Google Maps Platform tile service; availability and imagery dates vary by location.</p>
        <label className="settings-checkbox"><input type="checkbox" checked={enabled} onChange={event=>setEnabled(event.target.checked)} />Enable live Google imagery for this browser session</label>
        <label className="settings-key">Browser-restricted Maps API key<input type="password" autoComplete="off" spellCheck={false} value={key} onChange={event=>setKey(event.target.value)} placeholder="Enter your Maps JavaScript / Map Tiles API key" /></label>
        <p className="settings-note">Held in memory until this page reloads. Restrict the key to this site’s HTTP referrers and the Map Tiles API. Google requests use your project’s enabled API and billing; keys in a browser are visible to that browser.</p>
        {SHOWCASE && <p className="settings-notice">Reports remain a synthetic exercise. Enabling Google loads an external basemap; all other showcase providers stay offline.</p>}
        <a className="methods-link" href="https://developers.google.com/maps/documentation/tile/3d-tiles" target="_blank" rel="noopener noreferrer">Google setup, coverage and terms ↗</a>
        <h2>Service usage</h2><p>Measured model API usage and configured pricing, when available.</p><CostChip mono="var(--font-mono)" /><h2>Live data connections</h2><p>Collectors are configured on the server and disabled by default. Use your deployment configuration for provider credentials and explicitly enable collection. Transport connectivity alone does not establish source freshness.</p>
        {!SHOWCASE&&onOperatorKeyChange&&<><h2>Local briefing operator</h2><label className="settings-key">Operator key for generation<input type="password" autoComplete="off" spellCheck={false} value={operator} onChange={event=>setOperator(event.target.value)} placeholder="Optional · your server's administrator key"/></label><p className="settings-note">Optional, held only in this page's memory. Sent to your configured backend only after you explicitly request analysis or video. A page reload clears it. Viewing existing briefings does not require this key.</p></>}
        <p>Telegram sessions, model/provider API keys and other server secrets stay in server configuration. This application does not deliver an administrator key through public configuration or store the optional operator key in browser storage.</p>
      </div>
      <footer><span>{key ? "Key supplied · provider availability checked in Earth" : "No Google key supplied"}</span><button onClick={()=>{onOperatorKeyChange?.(operator.trim());onApply(key.trim(),enabled);}}>Apply settings →</button></footer>
    </section>
  </div>;
}
