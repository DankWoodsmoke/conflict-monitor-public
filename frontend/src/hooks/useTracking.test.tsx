import {act,useEffect} from "react";
import {createRoot,type Root} from "react-dom/client";
import {beforeEach,afterEach,describe,expect,it,vi} from "vitest";
import {useTracking} from "./useTracking";
import {apiFetch} from "../lib/api";
import {trackClock,earthMarkers} from "../lib/earth";
import {earthSymbol} from "../lib/earthSymbols";

vi.mock("../lib/api",()=>({apiFetch:vi.fn()}));
const fetchMock=vi.mocked(apiFetch);
let host:HTMLDivElement,root:Root,latest:ReturnType<typeof useTracking>;
const time=Date.parse("2026-10-10T12:00:00Z"),end=Date.parse("2026-10-29T03:00:00Z"),start=Date.parse("2026-02-28T00:00:00Z");
function Harness({cursor}:{cursor:number}){const result=useTracking({replayCursor:cursor,replayWindow:{start,end}});useEffect(()=>{latest=result;},[result]);return null;}
const snapshot=(stamp:number)=>({ts:new Date(stamp).toISOString(),aircraft:[{i:"abc123",c:"FIXTURE",la:0,lo:0,a:0,h:0,v:0,t:"",k:"",e:false,s:""}],vessels:[{m:"123456789",n:"Fixture",la:0,lo:0,sp:0,h:0,k:"",f:"",st:""}],jamming:[]});
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();vi.setSystemTime(end);fetchMock.mockReset().mockImplementation(async()=>Response.json([]));host=document.createElement("div");document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();});

describe("recorded tracking time slices",()=>{
 it("carries newly recorded observation clocks, quality and direction basis into Earth without rounding",async()=>{
  const row=snapshot(time),observed=new Date(time-5000).toISOString(),received=new Date(time-2000).toISOString();
  const recorded={...row,aircraft:[{...row.aircraft[0],la:30.12345678,lo:45.87654321,observed_at:observed,received_at:received,source:"adsb.lol",heading_basis:"course_over_ground",nic:8,nac_p:10,registration:"TEST-REG",altitude_reference:"geometric_reported"}],vessels:[{...row.vessels[0],h:55,course:0,heading_basis:"true_heading",observed_at:observed,received_at:received}]};
  fetchMock.mockImplementation(async(url)=>Response.json(String(url).includes("/snapshots?")?[recorded]:[]));
  await act(async()=>root.render(<Harness cursor={time+30000}/>));
  expect(latest.aircraft[0]).toMatchObject({lat:30.12345678,lon:45.87654321,observed_at:observed,received_at:received,heading_basis:"course_over_ground",nic:8,nac_p:10});
  expect(latest.vessels[0]).toMatchObject({heading:55,course:0,heading_basis:"true_heading",observed_at:observed});
  const markers=earthMarkers({events:[],aircraft:latest.aircraft,vessels:latest.vessels,hotspots:[],navigation:[],clock:time+30000,replaying:true});
  const ac=markers.find(m=>m.kind==="aircraft")!;
  expect(ac.lat).toBe(30.12345678);expect(ac.lon).toBe(45.87654321);expect(ac.positionState).toBe("recorded");
  expect(ac.details).toContainEqual(["Direction basis","Course over ground reported by provider"]);
  expect(ac.details).toContainEqual(["Reported position quality","NIC 8 / NACp 10 · provider categories, not a validated error radius"]);
  expect(ac.details.find(([key])=>key==="Observed")?.[1]).toContain("35s before displayed clock");
 });
 it("requests at most six hours around a replay cursor even when report history spans eight months",async()=>{
  await act(async()=>root.render(<Harness cursor={time}/>));
  const calls=fetchMock.mock.calls.filter(([url])=>String(url).includes("/snapshots?"));expect(calls).toHaveLength(1);
  const query=new URL(String(calls[0][0]),"http://localhost").searchParams,from=Date.parse(query.get("start")!),to=Date.parse(query.get("end")!);
  expect(to-from).toBeLessThanOrEqual(6*3600000);expect(from).toBeLessThanOrEqual(time);expect(to).toBeGreaterThan(time);
  expect(fetchMock.mock.calls.some(([url])=>String(url).includes("/tracking/tle"))).toBe(false);
 });
 it("uses capture time distinctly from observation time and expires against replay rather than wall time",async()=>{
  fetchMock.mockImplementation(async(url)=>Response.json(String(url).includes("/snapshots?")?[snapshot(time)]:[]));
  await act(async()=>root.render(<Harness cursor={time+60000}/>));
  expect(latest.aircraft).toHaveLength(1);expect(latest.aircraft[0].altitude).toBe(0);expect(latest.aircraft[0].observed_at).toBeUndefined();
  expect(trackClock(latest.aircraft[0],time+60000,120000)?.[0]).toBe("Snapshot captured · observation time unknown");
  await act(async()=>root.render(<Harness cursor={time+180000}/>));expect(latest.aircraft).toEqual([]);expect(latest.vessels).toHaveLength(1);
  await act(async()=>root.render(<Harness cursor={time+601000}/>));expect(latest.vessels).toEqual([]);
  expect(fetchMock.mock.calls.filter(([url])=>String(url).includes("/snapshots?"))).toHaveLength(1);
 });
 it("never uses a future snapshot or a live fallback to fill historical coverage",async()=>{
  fetchMock.mockImplementation(async(url)=>Response.json(String(url).includes("/snapshots?")?[snapshot(time+60000)]:[{icao24:"live",lat:1,lon:1}]));
  await act(async()=>root.render(<Harness cursor={time}/>));expect(latest.aircraft).toEqual([]);expect(latest.vessels).toEqual([]);
 });
 it("retains legacy replay direction including zero without inventing course or direction basis",async()=>{
  const row=snapshot(time);row.vessels.push({...row.vessels[0],m:"987654321",h:125});
  fetchMock.mockImplementation(async(url)=>Response.json(String(url).includes("/snapshots?")?[row]:[]));
  await act(async()=>root.render(<Harness cursor={time+60000}/>));
  expect(latest.vessels.map(v=>v.heading)).toEqual([0,125]);
  for(const vessel of latest.vessels){expect(vessel.course).toBeNull();expect(vessel.heading_basis).toBeUndefined();expect(vessel.nav_status).toBeNull();expect(vessel.lat).toBe(0);expect(vessel.lon).toBe(0);}
  expect(latest.aircraft[0].position_source).toBeNull();
 });
 it("preserves optional raw emitter category in future snapshots and never derives it from legacy heuristic k",async()=>{
  const row=snapshot(time),base=row.aircraft[0];
  const recorded={...row,aircraft:[{...base,i:"~894f5d",k:"civilian",ec:"C2"},{...base,i:"~894f54",k:"ground"},{...base,i:"abc123",k:"C3",ec:null}]};
  fetchMock.mockImplementation(async(url)=>Response.json(String(url).includes("/snapshots?")?[recorded]:[]));
  await act(async()=>root.render(<Harness cursor={time+60000}/>));
  expect(latest.aircraft.map(a=>a.category)).toEqual(["C2",undefined,undefined]);
  expect(latest.aircraft.map(a=>a.aircraft_category)).toEqual(["civilian","ground","C3"]);
  const markers=earthMarkers({events:[],aircraft:latest.aircraft,vessels:[],hotspots:[],navigation:[],clock:time+60000,replaying:true}).filter(m=>m.kind==="aircraft");
  expect(markers.map(earthSymbol)).toEqual(["ground","aircraft","aircraft"]);
  expect(markers.every(m=>m.positionState==="recorded")).toBe(true);
  expect(latest.aircraft.every(a=>a.observed_at===undefined&&a.snapshot_at===recorded.ts)).toBe(true);
  expect(markers.map(m=>m.id)).toEqual(["aircraft-~894f5d","aircraft-~894f54","aircraft-abc123"]);
 });
});
