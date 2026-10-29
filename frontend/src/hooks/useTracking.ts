import {useArrayPoll} from "./useArrayPoll";
import { apiFetch } from "../lib/api";
import { API_BASE } from "../lib/runtime";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export interface Aircraft {
  source?: string;
  altitude_reference?: string;
  snapshot_at?: string;
  icao24: string;
  callsign: string;
  origin_country: string;
  lat: number;
  lon: number;
  altitude: number | null;
  velocity: number | null;
  heading: number | null;
  on_ground: boolean;
  position_source: number;
  age_seconds?:number|null;
  observed_at?:string|null;
  received_at?:string|null;
  stale?:boolean;
  // Enriched ADS-B fields (optional — absent when using OpenSky fallback)
  type?: string;
  registration?: string;
  category?: string;
  aircraft_category?: string;
  squawk?: string;
  emergency?: string;
  is_emergency?: boolean;
  climb_rate?: number | null;
  ias?: number | null;
  tas?: number | null;
  mach?: number | null;
}

export interface TLERecord {
  name: string;
  line1?: string | null;
  line2?: string | null;
  omm?: Record<string, unknown>;
  epoch?: string;
  epoch_age_hours?: number;
}

export interface JammingZone {
  lat: number;
  lon: number;
  radius_km: number;
  aircraft_count: number;
  intensity: number;
}

export interface Vessel {
  snapshot_at?: string;
  mmsi: string;
  name: string;
  lat: number;
  lon: number;
  speed: number;
  heading: number;
  course: number;
  nav_status: number;
  age_seconds?:number|null;
  received_age_seconds?:number|null;
  observed_at?:string|null;
  received_at?:string|null;
  stale?:boolean|null;
  ship_type?: number;
  ship_type_name?: string;
  destination?: string;
  length?: number;
  callsign?: string;
  imo?: number;
  vessel_category?: string;
  flag_code?: string;
  flag_name?: string;
}

// Compact snapshot format from the backend
interface SnapshotData {
  ts: string;
  aircraft: Array<{
    i: string; c: string; la: number; lo: number;
    a: number | null; h: number | null; v: number | null;
    t: string; k: string; e: boolean; s: string;
    observed_at?:string|null;received_at?:string|null;source?:string;altitude_reference?:string;
  }>;
  vessels: Array<{
    m: string; n: string; la: number; lo: number;
    sp: number; h: number; k: string; f: string; st: string;
    observed_at?:string|null;received_at?:string|null;
  }>;
  jamming: Array<{
    la: number; lo: number; r: number; c: number; i: number;
  }>;
}

// Expand compact snapshot aircraft to full Aircraft interface
function expandAircraft(compact: SnapshotData["aircraft"],snapshotAt:string): Aircraft[] {
  return compact.map((a) => ({
    icao24: a.i,
    snapshot_at:snapshotAt,observed_at:a.observed_at,received_at:a.received_at,source:a.source,altitude_reference:a.altitude_reference,
    callsign: a.c,
    origin_country: "",
    lat: a.la,
    lon: a.lo,
    altitude: a.a,
    heading: a.h,
    velocity: a.v,
    on_ground: false,
    position_source: 0,
    type: a.t,
    aircraft_category: a.k,
    is_emergency: a.e,
    squawk: a.s,
  }));
}

function expandVessels(compact: SnapshotData["vessels"],snapshotAt:string): Vessel[] {
  return compact.map((v) => ({
    mmsi: v.m,
    snapshot_at:snapshotAt,observed_at:v.observed_at,received_at:v.received_at,
    name: v.n,
    lat: v.la,
    lon: v.lo,
    speed: v.sp,
    heading: v.h,
    course: v.h,
    nav_status: 0,
    vessel_category: v.k,
    flag_code: v.f,
    ship_type_name: v.st,
  }));
}

function expandJamming(compact: SnapshotData["jamming"]): JammingZone[] {
  return compact.map((z) => ({
    lat: z.la,
    lon: z.lo,
    radius_km: z.r,
    aircraft_count: z.c,
    intensity: z.i,
  }));
}

// Binary search: find the last snapshot with ts <= target
function findSnapshot(snapshots: SnapshotData[], targetMs: number): SnapshotData | null {
  let lo = 0, hi = snapshots.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    if (new Date(snapshots[mid].ts).getTime() <= targetMs) lo = mid + 1;
    else hi = mid - 1;
  }
  return hi >= 0 ? snapshots[hi] : null;
}


const AIRCRAFT_POLL_MS = 15_000;
const JAMMING_POLL_MS = 15_000;
const VESSEL_POLL_MS = 10_000;


interface UseTrackingOptions {
  replayCursor?: number | null;
  replayWindow?: { start: number; end: number } | null;
}

export function useTracking(options?: UseTrackingOptions) {
  const replayCursor = options?.replayCursor ?? null;
  const replayWindow = options?.replayWindow ?? null;
  const isReplaying = replayCursor != null;

  const {data:liveAircraft,status:aircraftStatus}=useArrayPoll<Aircraft>(`${API_BASE}/tracking/aircraft`,AIRCRAFT_POLL_MS,120000,!isReplaying);
  const {data:liveVessels,status:vesselStatus}=useArrayPoll<Vessel>(`${API_BASE}/tracking/vessels`,VESSEL_POLL_MS,600000,!isReplaying);
  const {data:liveJamming,status:navigationStatus}=useArrayPoll<JammingZone>(`${API_BASE}/tracking/jamming`,JAMMING_POLL_MS,120000,!isReplaying);
  // Orbital elements remain an optional backend API; unqualified orbital markers are not part of Earth.
  const tleData:TLERecord[]=[];
  const [snapshots,setSnapshots]=useState<SnapshotData[]>([]);
  const [snapshotWindow,setSnapshotWindow]=useState("");
  const [loadingSnapshots,setLoadingSnapshots]=useState(false);

  // Six-hour slices retain the recorder's full cadence and work for a months-long report domain.
  // Bucket by logical replay time, not every animation frame, to bound requests during playback.
  const bucket=isReplaying?Math.floor(replayCursor/(2*3600000)):null;
  const requestStart=bucket==null?null:Math.max(replayWindow?.start??0,(bucket-1)*2*3600000);
  const requestEnd=bucket==null?null:Math.min(replayWindow?.end??Infinity,(bucket+2)*2*3600000);
  useEffect(()=>{
    if(requestStart==null||requestEnd==null||requestEnd<requestStart){setSnapshots([]);setSnapshotWindow("");setLoadingSnapshots(false);return;}
    const key=`${requestStart}-${requestEnd}`;
    const controller=new AbortController();let cancelled=false;
    setLoadingSnapshots(true);
    const start=new Date(requestStart).toISOString(),end=new Date(requestEnd).toISOString();
    apiFetch(`${API_BASE}/tracking/snapshots?start=${start}&end=${end}`,{signal:controller.signal})
      .then(async r=>{if(!r.ok)throw new Error("Snapshot unavailable");const rows:unknown=await r.json();if(!Array.isArray(rows))throw new Error("Invalid snapshot");return rows as SnapshotData[];})
      .then(rows=>{if(!cancelled){setSnapshots(rows.filter(row=>row&&Number.isFinite(Date.parse(row.ts))&&Array.isArray(row.aircraft)&&Array.isArray(row.vessels)&&Array.isArray(row.jamming)).sort((a,b)=>Date.parse(a.ts)-Date.parse(b.ts)));setSnapshotWindow(key);}})
      .catch(()=>{if(!cancelled){setSnapshots([]);setSnapshotWindow("");}})
      .finally(()=>{if(!cancelled)setLoadingSnapshots(false);});
    return()=>{cancelled=true;controller.abort();};
  },[requestStart,requestEnd]);

  // ── Resolve current data (live or snapshot) ────────────────────────────
  const snapshotResult = useMemo(() => {
    if (!isReplaying || snapshots.length === 0) return null;
    return findSnapshot(snapshots, replayCursor);
  }, [isReplaying, replayCursor, snapshots]);

  const aircraft = useMemo(() => {
    if (snapshotResult) return (replayCursor??Infinity)-Date.parse(snapshotResult.ts)<=120000?expandAircraft(snapshotResult.aircraft,snapshotResult.ts):[];
    return isReplaying ? [] : liveAircraft;
  }, [snapshotResult, liveAircraft, isReplaying,replayCursor]);

  const vessels = useMemo(() => {
    if (snapshotResult) return (replayCursor??Infinity)-Date.parse(snapshotResult.ts)<=600000?expandVessels(snapshotResult.vessels,snapshotResult.ts):[];
    return isReplaying ? [] : liveVessels;
  }, [snapshotResult, liveVessels, isReplaying,replayCursor]);

  const jammingZones = useMemo(() => {
    if (snapshotResult) return (replayCursor??Infinity)-Date.parse(snapshotResult.ts)<=120000?expandJamming(snapshotResult.jamming):[];
    return isReplaying ? [] : liveJamming;
  }, [snapshotResult, liveJamming, isReplaying,replayCursor]);

  return { aircraft, tleData, jammingZones, vessels, loadingSnapshots, snapshotAt:snapshotResult?.ts??null, trackingStatus:{aircraft:aircraftStatus,vessels:vesselStatus,navigation:navigationStatus} };
}
