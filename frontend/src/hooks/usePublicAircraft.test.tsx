import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {beforeEach,afterEach,expect,it,vi} from "vitest";
import {usePublicAircraft} from "./usePublicAircraft";
import {apiFetch} from "../lib/api";
import {validPublicAircraft,validPublicObservations} from "../lib/publicData";

vi.mock("../lib/api",()=>({apiFetch:vi.fn()}));
const now="2026-11-06T03:00:00Z";
const packet=()=>({source:"adsb_lol",license:"ODbL-1.0",status:"fresh",batch_id:"a".repeat(64),published_at:now,aircraft:[{source:"adsb.lol",icao24:"abc123",lat:29,lon:44,observed_at:now,received_at:now,normalized_record_sha256:"b".repeat(64)}]});
let root:Root,host:HTMLDivElement;
function Panel({enabled}:{enabled:boolean}){const result=usePublicAircraft(enabled);return <div data-failed={result.failed} data-count={result.aircraft.length}/>;}
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();vi.setSystemTime(new Date(now));vi.mocked(apiFetch).mockReset();host=document.createElement("div");document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();});

it("withholds disabled data; hung refresh clears positions and a new signal recovers",async()=>{
 let calls=0;const signals:AbortSignal[]=[];
 vi.mocked(apiFetch).mockImplementation(async(_url,init)=>{signals.push(init!.signal as AbortSignal);calls++;return calls===2?new Promise<Response>(()=>{}):Response.json(packet());});
 await act(async()=>root.render(<Panel enabled={false}/>));
 await act(async()=>vi.advanceTimersByTimeAsync(60000));expect(calls).toBe(0);
 await act(async()=>root.render(<Panel enabled/>));expect(host.querySelector('[data-count="1"]')).not.toBeNull();
 await act(async()=>vi.advanceTimersByTimeAsync(15000));expect(calls).toBe(2);
 await act(async()=>vi.advanceTimersByTimeAsync(15000));expect(host.querySelector('[data-count="0"][data-failed="true"]')).not.toBeNull();expect(signals[1].aborted).toBe(true);expect(calls).toBe(2);
 await act(async()=>vi.advanceTimersByTimeAsync(15000));expect(calls).toBe(3);expect(signals[2]).not.toBe(signals[1]);expect(signals[2].aborted).toBe(false);expect(host.querySelector('[data-count="1"][data-failed="false"]')).not.toBeNull();
});

it("rejects wrong source, malformed coordinates, clocks and batch identity",()=>{
 expect(validPublicAircraft(packet())).toBe(true);
 for(const change of [(p:any)=>p.source="private",(p:any)=>p.batch_id="private-id",(p:any)=>p.aircraft[0].lat=999,(p:any)=>p.aircraft[0].observed_at="unknown",(p:any)=>p.aircraft[0].source="opensky"]){const p=packet();change(p);expect(validPublicAircraft(p)).toBe(false);}
 expect(validPublicObservations({source:"private",status:"fresh",hotspots:[]})).toBe(false);
});

it("rejects duplicate published aircraft and normalized thermal positions before Earth rendering",()=>{
 const aircraft=packet();aircraft.aircraft.push({...aircraft.aircraft[0]});expect(validPublicAircraft(aircraft)).toBe(false);
 const pixel={id:"b".repeat(64),lat:29,lon:44,frp:25,ts:now,source_row_sha256:"c".repeat(64),satellite:"NOAA-20",instrument:"VIIRS",confidence_label:"nominal"};
 const thermal={source:"nasa_firms_noaa20",status:"fresh",batch_id:"a".repeat(64),published_at:now,eligible_count:2,displayed_count:2,hotspots:[pixel,{...pixel,id:"d".repeat(64),ts:"2026-11-05T22:00:00-05:00",frp:30}]};
 expect(validPublicObservations(thermal)).toBe(false);
 thermal.hotspots[1]={...pixel,lat:29.1};expect(validPublicObservations(thermal)).toBe(false);
 thermal.hotspots[1]={...pixel,id:"d".repeat(64),lat:29.1};expect(validPublicObservations(thermal)).toBe(true);
 thermal.eligible_count=1;expect(validPublicObservations(thermal)).toBe(false);
});
