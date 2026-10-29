import {act,useEffect} from "react";
import {createRoot,type Root} from "react-dom/client";
import {beforeEach,afterEach,describe,expect,it,vi} from "vitest";
import {useTracking} from "./useTracking";
import {apiFetch} from "../lib/api";
import {trackClock} from "../lib/earth";

vi.mock("../lib/api",()=>({apiFetch:vi.fn()}));
const fetchMock=vi.mocked(apiFetch);
let host:HTMLDivElement,root:Root,latest:ReturnType<typeof useTracking>;
const time=Date.parse("2026-10-10T12:00:00Z"),end=Date.parse("2026-10-29T03:00:00Z"),start=Date.parse("2026-02-28T00:00:00Z");
function Harness({cursor}:{cursor:number}){const result=useTracking({replayCursor:cursor,replayWindow:{start,end}});useEffect(()=>{latest=result;},[result]);return null;}
const snapshot=(stamp:number)=>({ts:new Date(stamp).toISOString(),aircraft:[{i:"abc123",c:"FIXTURE",la:0,lo:0,a:0,h:0,v:0,t:"",k:"",e:false,s:""}],vessels:[{m:"123456789",n:"Fixture",la:0,lo:0,sp:0,h:0,k:"",f:"",st:""}],jamming:[]});
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();vi.setSystemTime(end);fetchMock.mockReset().mockImplementation(async()=>Response.json([]));host=document.createElement("div");document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();});

describe("recorded tracking time slices",()=>{
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
});
