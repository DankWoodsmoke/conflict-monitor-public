import type {ConflictEvent} from "../types/event";
import type {Aircraft,Vessel,JammingZone} from "../hooks/useTracking";
import {severityLabel} from "./events";
import {BASES,CHOKEPOINTS,REFINERIES,AIRFIELDS} from "./earthReference";

export type EarthKind="report"|"aircraft"|"vessel"|"thermal"|"reference"|"navigation";
export type PositionState="fresh"|"last_known"|"recorded"|"synthetic";
export type EarthMarker={id:string;kind:EarthKind;name:string;lat:number;lon:number;height:number;color:string;details:Array<[string,string]>;url?:string;report?:ConflictEvent;radius?:number;heading?:number|null;positionState?:PositionState};
export type ThermalObservation={lat:number;lon:number;frp:number;ts:string;conf:number|null;confidence_label?:string;google_maps_url?:string;eo_browser_url?:string;probable_flare?:boolean;flare_zone?:string;stale?:boolean};
export type EarthLayers=Record<EarthKind,boolean> & {routes:boolean;lastKnown:boolean};
export const DEFAULT_EARTH_LAYERS:EarthLayers={report:true,aircraft:true,vessel:true,thermal:false,reference:false,navigation:false,routes:false,lastKnown:true};
export function enabledEarthMarkers(markers:EarthMarker[],layers:EarthLayers){return markers.filter(marker=>layers[marker.kind]&&(layers.lastKnown||marker.positionState!=="last_known"));}
export const validCoordinates=(lat:unknown,lon:unknown):boolean=>typeof lat==="number"&&typeof lon==="number"&&Number.isFinite(lat)&&Number.isFinite(lon)&&lat>=-90&&lat<=90&&lon>=-180&&lon<=180;
export const utc=(value:string)=>Number.isFinite(Date.parse(value))?new Date(value).toISOString().replace("T"," ").replace(/\.\d{3}Z$/," UTC"):"Unknown";
export function coordinateLabel(lat:number,lon:number){return `${Math.abs(lat).toFixed(4)}°${lat<0?"S":"N"}, ${Math.abs(lon).toFixed(4)}°${lon<0?"W":"E"}`;}
const finite=(value:unknown,unit:string)=>typeof value==="number"&&Number.isFinite(value)?`${Math.round(value*10)/10} ${unit}`:"Unknown";
const COLORS:Record<string,string>={military:"#f27c74",diplomatic:"#77b9eb",economic:"#dcb969",cyber:"#bf9bea",humanitarian:"#91d0ad",protest:"#d7a5cf",thermal_anomaly:"#e4a069",unclassified:"#c3d6de"};

/** Do not confuse a capture/receipt clock with the originating observation clock. */
export function trackClock(row:{observed_at?:string|null;received_at?:string|null;snapshot_at?:string|null;stale?:boolean|null},clock:number,ttl:number,synthetic=false):[string,string]|null{
  if(synthetic)return ["Clock","Synthetic exercise reference"];
  for(const [label,value] of [["Observed",row.observed_at],["Snapshot captured · observation time unknown",row.snapshot_at],["Received · observation time unknown",row.received_at]] as const){
    if(typeof value!=="string"||!/(Z|[+-]\d{2}:\d{2})$/i.test(value))continue;
    const time=Date.parse(value),age=clock-time;
    if(!Number.isFinite(time)||age< -60000||age>ttl)return null;
    return [label,`${utc(value)} · ${age<0?`${Math.ceil(-age/1000)}s ahead of displayed clock`:`${Math.floor(age/1000)}s before displayed clock`}`];
  }
  return null;
}

/** A retained observation never becomes fresh by being fetched or rendered again. */
function positionState(row:{observed_at?:string|null;snapshot_at?:string|null;stale?:boolean|null},clock:number,freshMs:number,synthetic=false,replaying=false):PositionState{
  if(synthetic)return "synthetic";
  if(replaying||row.snapshot_at)return "recorded";
  const observed=typeof row.observed_at==="string"?Date.parse(row.observed_at):NaN,age=clock-observed;
  return row.stale===true||!Number.isFinite(age)||age<0||age>freshMs?"last_known":"fresh";
}
const positionStateLabel=(state:PositionState)=>state==="fresh"?"Fresh source observation; no motion extrapolation":state==="last_known"?"Last-known observation · not a current position":state==="recorded"?"Recorded snapshot · not a live position":"Synthetic exercise position";

export function reportCameraRange(event:ConflictEvent):number{
  return {site:10000,sensor_pixel:30000,city:90000,region:650000,country:2200000,unknown:1000000}[event.geolocation_precision||"unknown"];
}

export function earthMarkers(options:{events:ConflictEvent[];aircraft:Aircraft[];vessels:Vessel[];hotspots:ThermalObservation[];navigation:JammingZone[];clock:number;synthetic?:boolean;windowStart?:number;replaying?:boolean}):EarthMarker[]{
  const result:EarthMarker[]=[];
  for(const event of options.events){
    if(!validCoordinates(event.lat,event.lon))continue;
    result.push({id:`report-${event.id}`,kind:"report",name:event.summary,lat:event.lat!,lon:event.lon!,height:0,color:COLORS[event.event_type]||COLORS.unclassified,report:event,url:event.source_url,
      details:[["Source",event.channel_name||event.source],["Source publication",`${utc(event.timestamp)} · incident time unverified`],["Location precision",event.geolocation_precision||"Unknown"],["Coordinates",coordinateLabel(event.lat!,event.lon!)],["Severity",severityLabel(event)],["Position display","Surface marker; no measured event altitude"]]});
  }
  for(const ac of options.aircraft){
    const clock=trackClock(ac,options.clock,120000,options.synthetic);
    if(!validCoordinates(ac.lat,ac.lon)||!clock)continue;
    const state=positionState(ac,options.clock,45000,options.synthetic,options.replaying);
    result.push({id:`aircraft-${ac.icao24}`,kind:"aircraft",name:ac.callsign?.trim()||ac.icao24,lat:ac.lat,lon:ac.lon,height:0,color:ac.is_emergency?"#f69d84":"#8fd3f5",heading:ac.heading,positionState:state,
      details:[["ICAO",ac.icao24],["Source",ac.source||"Tracking provider"],["Position state",positionStateLabel(state)],clock,["Coordinates",coordinateLabel(ac.lat,ac.lon)],["Reported altitude",finite(ac.altitude,"m")],["Vertical reference",ac.altitude_reference||"Mixed provider reference; not established as ellipsoid height"],["Speed",finite(ac.velocity,"m/s")],["Heading",finite(ac.heading,"degrees")],["Position display","Surface projection; aircraft height is not inferred"],["Coverage","Partial receiver coverage; absence is not evidence of no aircraft"]]});
  }
  for(const vessel of options.vessels){
    const clock=trackClock(vessel,options.clock,600000,options.synthetic);
    if(!validCoordinates(vessel.lat,vessel.lon)||!clock)continue;
    const state=positionState(vessel,options.clock,120000,options.synthetic,options.replaying);
    result.push({id:`vessel-${vessel.mmsi}`,kind:"vessel",name:vessel.name||vessel.mmsi,lat:vessel.lat,lon:vessel.lon,height:0,color:"#79d6c5",heading:vessel.heading,positionState:state,
      details:[["MMSI",vessel.mmsi],["Source","AISStream · identity and flag are reported"],["Position state",positionStateLabel(state)],clock,["Coordinates",coordinateLabel(vessel.lat,vessel.lon)],["Speed",finite(vessel.speed,"knots")],["Heading",finite(vessel.heading,"degrees")],["Course",finite(vessel.course,"degrees")],["Destination",vessel.destination||"Unknown"],["Position display","Surface projection; not a surveyed sea-level height"]]});
  }
  for(const hot of options.hotspots){
    const time=Date.parse(hot.ts),age=options.clock-time;
    if(!validCoordinates(hot.lat,hot.lon)||!Number.isFinite(time)||age<0||age>48*3600000||hot.stale===true||(options.windowStart!=null&&time<options.windowStart))continue;
    result.push({id:`thermal-${hot.lat}-${hot.lon}-${hot.ts}`,kind:"thermal",name:`VIIRS thermal observation · ${finite(hot.frp,"MW")}`,lat:hot.lat,lon:hot.lon,height:0,color:"#f1b16e",url:hot.eo_browser_url,
      details:[["Source","NASA FIRMS · VIIRS"],["Acquired",utc(hot.ts)],["Coordinates",coordinateLabel(hot.lat,hot.lon)],["Fire radiative power",finite(hot.frp,"MW")],["Native confidence",hot.confidence_label||(hot.conf==null?"Unknown":String(hot.conf))],["Interpretation","Thermal detection; cause, actor and casualties unassessed"],...(hot.probable_flare?[["Regional overlap",`Industrial region only; cause unassessed ${hot.flare_zone||""}`] as [string,string]]:[])]});
  }
  for(const [i,z] of options.navigation.entries()){
    if(options.replaying||!validCoordinates(z.lat,z.lon)||!Number.isFinite(z.radius_km)||z.radius_km<=0||z.radius_km>1000)continue;
    result.push({id:`navigation-${i}`,kind:"navigation",name:"Navigation-quality candidate",lat:z.lat,lon:z.lon,height:0,radius:z.radius_km*1000,color:"#c7a4e8",details:[["Contributing tracks",String(z.aircraft_count)],["Heuristic radius",finite(z.radius_km,"km")],["Interpretation","Position-quality clustering only; does not establish interference, cause or attribution"]]});
  }
  for(const place of [...CHOKEPOINTS,...BASES,...REFINERIES,...AIRFIELDS])result.push({id:`reference-${place.name}`,kind:"reference",name:place.name,lat:place.lat,lon:place.lng,height:0,color:"#adb4c4",details:[["Dataset","Inherited reference infrastructure"],["Source / survey date","Unverified; retained from recovered application"],["Coordinates",coordinateLabel(place.lat,place.lng)],["Precision","Approximate reference point; not an operational observation"],["Current status / ownership","Unverified"]]});
  return result;
}

export const CAMERA_PLACES=[{name:"Region",lat:29,lon:44,range:3500000},{name:"Levant",lat:32,lon:35,range:700000},{name:"Gulf",lat:25,lon:52,range:1100000},{name:"Tehran",lat:35.69,lon:51.39,range:120000},{name:"Tel Aviv",lat:32.08,lon:34.78,range:90000},{name:"Dubai",lat:25.2,lon:55.27,range:110000},{name:"Beirut",lat:33.89,lon:35.5,range:90000},{name:"Gaza",lat:31.5,lon:34.46,range:110000},{name:"Strait of Hormuz",lat:26.6,lon:56.5,range:350000}];
export function parseCoordinates(text:string):{lat:number;lon:number}|null{
  const match=text.trim().match(/^(-?\d+(?:\.\d+)?)\s*[,\s]\s*(-?\d+(?:\.\d+)?)$/);
  if(!match)return null;const lat=Number(match[1]),lon=Number(match[2]);return validCoordinates(lat,lon)?{lat,lon}:null;
}
