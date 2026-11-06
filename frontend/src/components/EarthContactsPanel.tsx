import {useEffect,useMemo,useState} from "react";
import type {EarthMarker} from "../lib/earth";
import {coordinateLabel} from "../lib/earth";
import {EARTH_SYMBOLS,earthMarkerSearchText,earthSymbol,earthSymbolImage} from "../lib/earthSymbols";

export const positionStateText=(marker:EarthMarker)=>marker.positionState==="fresh"?"Fresh observation":marker.positionState==="last_known"?"Last known":marker.positionState==="recorded"?"Recorded":marker.positionState==="synthetic"?"Synthetic":"Observation time unknown";
const matches=(marker:EarthMarker,query:string,kind:string)=>(kind==="all"||marker.kind===kind)&&earthMarkerSearchText(marker).includes(query.trim().toLowerCase());
const ordered=(markers:EarthMarker[],query:string,kind:string)=>markers.filter(marker=>matches(marker,query,kind)).sort((a,b)=>a.name.localeCompare(b.name)||a.id.localeCompare(b.id));
const oneLine={whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"} as const;

/** The index always searches all members, including contacts hidden behind a group badge. */
export function EarthContactsPanel({markers,areaGroup,onChoose,onZoom,onClose}:{markers:EarthMarker[];areaGroup:boolean;onChoose:(marker:EarthMarker)=>void;onZoom:()=>void;onClose:()=>void}){
  const [query,setQuery]=useState(""),[kind,setKind]=useState("all"),[limit,setLimit]=useState(40);
  const current=useMemo(()=>new Map(markers.map(marker=>[marker.id,marker])),[markers]);
  const [slots,setSlots]=useState(()=>ordered(markers,"","all"));
  useEffect(()=>setSlots(previous=>{
    // Preserve row identity and order across polls. Departed IDs keep a disabled
    // slot. New IDs require an explicit refresh, so open panels cannot grow forever.
    return previous.map(marker=>current.get(marker.id)||marker);
  }),[current]);
  const changeSearch=(nextQuery:string,nextKind:string)=>{setQuery(nextQuery);setKind(nextKind);setLimit(40);setSlots(ordered(markers,nextQuery,nextKind));};
  const currentCount=slots.filter(marker=>current.has(marker.id)).length,unavailable=slots.length-currentCount;
  const slotIds=new Set(slots.map(marker=>marker.id)),newCount=markers.filter(marker=>!slotIds.has(marker.id)&&matches(marker,query,kind)).length;
  return <>
    <div className="earth-panel-heading"><h2 style={{...oneLine,minWidth:0}}>{areaGroup?"Area group":"Visible contacts"} · {markers.length}</h2><button onClick={onClose} aria-label="Close contacts">×</button></div>
    <p>{areaGroup?"Grouped by screen area. The badge is a display label, not a shared location.":"Source positions inside the current camera view."} Select a contact to inspect its original coordinate and source clock.</p>
    <div className="earth-contact-actions"><button onClick={onZoom} disabled={!markers.length} style={{flex:1}}>Zoom to {areaGroup?"group":"contacts"}</button><button onClick={()=>changeSearch(query,kind)} style={{flex:1}}>Refresh contacts</button></div>
    <label className="earth-contact-search">Search all {markers.length} contacts<input value={query} onChange={e=>changeSearch(e.target.value,kind)} placeholder="Callsign, MMSI, registration or ID"/></label>
    <label className="earth-contact-kind">Contact type<select value={kind} onChange={e=>changeSearch(query,e.target.value)}><option value="all">All types</option><option value="aircraft">ADS-B emitters</option><option value="vessel">Vessels</option></select></label>
    <p className="earth-contact-count" role="status"><span style={{...oneLine,display:"block"}}>{currentCount} current · {unavailable} unavailable · {Math.min(limit,slots.length)} shown.</span><span style={{...oneLine,display:"block"}}>{newCount} new matching contacts · refresh to include.</span>Rows stay in place until you refresh or change search or type.</p>
    <ul className="earth-contact-list" style={{gridTemplateColumns:"minmax(0, 1fr)",minWidth:0}}>{slots.slice(0,limit).map(previous=>{
      const live=current.get(previous.id),marker=live||previous;
      const symbol=earthSymbol(marker),clock=marker.details.find(([name])=>/^(Observed|Snapshot captured|Received|Clock)/.test(name));
      const state=live?positionStateText(marker):"No longer in current selection";
      const coordinate=`${live?"":"Last displayed · "}${coordinateLabel(marker.lat,marker.lon)}`;
      const clockText=clock?`${live?"":"Last displayed · "}${clock[0]} · ${clock[1]}`:"Source clock unavailable";
      return <li key={marker.id} style={{minWidth:0}}><button data-contact-id={marker.id} disabled={!live} style={{height:124,width:"100%",minWidth:0,boxSizing:"border-box",overflow:"hidden"}} title={[marker.name,EARTH_SYMBOLS[symbol].label,marker.identifier,state,coordinate,clockText].filter(Boolean).join("\n")} onClick={()=>{const latest=current.get(marker.id);if(latest)onChoose(latest);}}><img alt="" width={32} height={32} src={earthSymbolImage(symbol,marker.color,!live||marker.positionState==="last_known"||marker.positionState==="recorded")}/><span style={{minWidth:0,flex:1}}><strong style={oneLine}>{marker.name}</strong><small style={oneLine}>{EARTH_SYMBOLS[symbol].label} · {marker.identifier}</small><small style={oneLine} className={`earth-contact-state ${live?marker.positionState||"unknown":"unknown"}`}>{state}</small><small style={oneLine}>{coordinate}</small><small style={oneLine}>{clockText}</small></span></button></li>;
    })}</ul>
    {!currentCount&&<p>No matching contacts remain in this selection. Try another search or reopen the current view.</p>}
    {limit<slots.length&&<button className="earth-contact-more" onClick={()=>setLimit(value=>value+40)}>Show 40 more contacts</button>}
  </>;
}
