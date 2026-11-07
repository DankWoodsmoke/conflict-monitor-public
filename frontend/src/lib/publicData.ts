import {validCoordinates} from "./earth";
import type {PublicObservations} from "../hooks/usePublicObservations";
import type {PublicAircraft} from "../hooks/usePublicAircraft";

const record=(v:unknown):v is Record<string,any>=>!!v&&typeof v==="object"&&!Array.isArray(v);
const hash=(v:unknown):v is string=>typeof v==="string"&&/^[a-f0-9]{64}$/.test(v);
const clock=(v:unknown):v is string=>typeof v==="string"&&v.length<=40&&/(Z|[+-]\d{2}:\d{2})$/.test(v)&&Number.isFinite(Date.parse(v));
const statuses=["fresh","empty","stale","awaiting_publication","failed"];
function envelope(value:unknown,source:string):value is Record<string,any>{
 if(!record(value)||value.source!==source||!statuses.includes(value.status))return false;
 if(value.batch_id!==null&&!hash(value.batch_id))return false;
 if(value.published_at!==null&&(!clock(value.published_at)||Date.parse(value.published_at)>Date.now()+300000))return false;
 return !["fresh","empty","stale"].includes(value.status)||(hash(value.batch_id)&&clock(value.published_at));
}
export function validPublicObservations(value:unknown):value is PublicObservations{
 if(!envelope(value,"nasa_firms_noaa20")||!Array.isArray(value.hotspots)||value.hotspots.length>2000)return false;
 if(!Number.isInteger(value.eligible_count)||value.eligible_count<value.hotspots.length||value.eligible_count>10000||value.displayed_count!==value.hotspots.length)return false;
 if(!value.hotspots.every((p:unknown)=>record(p)&&hash(p.id)&&hash(p.source_row_sha256)&&validCoordinates(p.lat,p.lon)&&p.lat>=10&&p.lat<=42&&p.lon>=25&&p.lon<=65&&typeof p.frp==="number"&&Number.isFinite(p.frp)&&p.frp>=10&&clock(p.ts)&&Date.parse(p.ts)<=Date.now()+300000&&p.satellite==="NOAA-20"&&p.instrument==="VIIRS"&&["low","nominal","high","unknown"].includes(p.confidence_label)))return false;
 const ids=new Set(value.hotspots.map((p:Record<string,any>)=>p.id));
 const positions=new Set(value.hotspots.map((p:Record<string,any>)=>JSON.stringify([p.lat,p.lon,Date.parse(p.ts)])));
 return ids.size===value.hotspots.length&&positions.size===value.hotspots.length;
}
export function validPublicAircraft(value:unknown):value is PublicAircraft{
 if(!envelope(value,"adsb_lol")||value.license!=="ODbL-1.0"||!Array.isArray(value.aircraft)||value.aircraft.length>5000)return false;
 return value.aircraft.every((p:unknown)=>record(p)&&p.source==="adsb.lol"&&typeof p.icao24==="string"&&/^~?[a-f0-9]{6}$/.test(p.icao24)&&hash(p.normalized_record_sha256)&&validCoordinates(p.lat,p.lon)&&clock(p.observed_at)&&clock(p.received_at)&&Date.parse(p.observed_at)<=Date.now()+60000)&&new Set(value.aircraft.map((p:Record<string,any>)=>p.icao24)).size===value.aircraft.length;
}
