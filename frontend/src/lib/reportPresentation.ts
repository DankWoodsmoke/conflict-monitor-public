import type {ConflictEvent} from "../types/event";
import {validCoordinates} from "./earth";
import {reportSourceKind as sourceFamily} from "./events";
export {sourceFamily};

/** Loaded source records, not incident counts or a priority assessment. */
export function recentReports(events:ConflictEvent[],clock:number,hours:number):ConflictEvent[]{
 return events.filter(event=>{const time=Date.parse(event.timestamp);return Number.isFinite(time)&&time<=clock&&clock-time<=hours*3600000;}).sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp)||b.id-a.id);
}
export type SourceFamily="telegram"|"x"|"rss"|"sensor"|"other";
export function sourceFamilyCounts(events:ConflictEvent[]):Record<SourceFamily,number>{
 const counts={telegram:0,x:0,rss:0,sensor:0,other:0};for(const event of events)counts[sourceFamily(event)]++;return counts;
}
export function sourceAge(timestamp:unknown,clock:number):string{
 const time=typeof timestamp==="string"?Date.parse(timestamp):NaN;
 if(!Number.isFinite(time))return "Time unknown";
 if(time>clock)return "Future source time";
 const seconds=Math.floor((clock-time)/1000);return seconds<60?`${seconds}s`:seconds<3600?`${Math.floor(seconds/60)}m`:`${Math.floor(seconds/3600)}h`;
}
/** Provider context links do not assert imagery date, resolution or incident proof. */
export function reportImageryLinks(event:Pick<ConflictEvent,"lat"|"lon"|"timestamp">){
 if(!validCoordinates(event.lat,event.lon))return {google:null,worldview:null,copernicus:null};
 const lat=event.lat!,lon=event.lon!,time=Date.parse(event.timestamp);
 return {
  google:`https://www.google.com/maps/@${lat.toFixed(5)},${lon.toFixed(5)},17z/data=!3m1!1e3`,
  worldview:Number.isFinite(time)?`https://worldview.earthdata.nasa.gov/?v=${lon-.12},${lat-.12},${lon+.12},${lat+.12}&t=${new Date(time).toISOString().slice(0,10)}&l=VIIRS_NOAA20_Thermal_Anomalies_375m_Night,VIIRS_NOAA20_CorrectedReflectance_TrueColor&lg=false`:null,
  copernicus:`https://browser.dataspace.copernicus.eu/?zoom=14&lat=${lat.toFixed(4)}&lng=${lon.toFixed(4)}&themeId=DEFAULT-THEME&datasetId=S2L2A`,
 };
}
