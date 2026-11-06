import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import App from "./App";
import {apiFetch} from "./lib/api";

vi.mock("./components/CesiumView",()=>({CesiumView:({readOnly,firmsHotspots=[]}:{readOnly:boolean;firmsHotspots:unknown[]})=><div className="earth-canvas" data-read-only={readOnly} data-thermal-count={firmsHotspots.length}><canvas/>Earth renderer fixture</div>}));
vi.mock("./lib/api",()=>({apiFetch:vi.fn()}));

const publicConfig={public_read_only:true,public_reports_enabled:false,public_tracking_enabled:false,
 public_media_enabled:false,public_notice:"Reports withheld pending publication approval.",google_earth_enabled:false};
let host:HTMLDivElement,root:Root,sockets:ReturnType<typeof vi.fn>;
const requested=()=>vi.mocked(apiFetch).mock.calls.map(([url])=>new URL(String(url),"http://localhost").pathname);
beforeEach(()=>{
 (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();
 window.history.replaceState(null,"","/?view=earth");
 sockets=vi.fn(function(){throw Error("A withheld public report stream must not create a socket");});
 vi.stubGlobal("WebSocket",sockets);
 vi.mocked(apiFetch).mockReset().mockImplementation(async input=>Response.json(String(input).endsWith("/config")?publicConfig:{...publicConfig,mode:"public_read_only"}));
 host=document.createElement("div");document.body.append(host);root=createRoot(host);
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.unstubAllGlobals();vi.useRealTimers();});

describe("public reader capability boundaries",()=>{
 it.each([
  [false,false,"datasets withheld","Historical reports are withheld pending publication approval. No live coverage is claimed."],
  [true,false,"thermal context enabled","NASA thermal context · no verified strike, cause, actor or casualty claim."],
  [false,true,"aircraft context enabled","Selected aircraft observations · identity, ownership, mission and intent are unverified; coverage is incomplete."],
  [true,true,"thermal + aircraft context enabled","NASA thermal context and selected aircraft observations · no verified strike, mission or complete conflict coverage claim."],
 ])("names only the dedicated public capabilities: thermal=%s aircraft=%s",async(thermal,aircraft,label,notice)=>{
  vi.mocked(apiFetch).mockImplementation(async input=>Response.json(String(input).endsWith("/config")?
   {...publicConfig,public_observations_enabled:thermal,public_aircraft_enabled:aircraft}:{...publicConfig,mode:"public_read_only"}));
  await act(async()=>root.render(<App/>));
  expect(host.querySelector(".source-runtime-label")?.textContent).toBe(`Public research · ${label}`);
  expect(host.querySelector(".timeline-wrap")?.textContent).toBe(notice);
  expect(host.querySelector(".source-runtime-label")?.textContent).not.toContain("tracking withheld");
  expect(host.querySelector("main.public-data-workspace")).not.toBeNull();
  expect(host.querySelector(".public-attribution-wrap")!==null).toBe(aircraft);
  expect(sockets).not.toHaveBeenCalled();
 });
 it("keeps admitted aircraft attribution outside the optional market strip across all tabs",async()=>{
  const batch="a".repeat(64),now=new Date().toISOString();
  const aircraft={source:"adsb_lol",license:"ODbL-1.0",status:"fresh",batch_id:batch,published_at:now,
   aircraft:[{source:"adsb.lol",icao24:"abc123",lat:29,lon:44,observed_at:now,received_at:now,normalized_record_sha256:"b".repeat(64)}]};
  vi.mocked(apiFetch).mockImplementation(async input=>Response.json(String(input).endsWith("/config")?
   {...publicConfig,public_aircraft_enabled:true}:String(input).endsWith("/publication/aircraft")?aircraft:{...publicConfig,mode:"public_read_only"}));
  await act(async()=>root.render(<App/>));
  const canvas=host.querySelector("canvas"),attribution=host.querySelector(".public-data-attribution");
  for(const name of ["Media","Brief","Earth"]){
   const button=[...host.querySelectorAll<HTMLButtonElement>(".view-tab-group button")].find(node=>node.textContent===name)!;
   await act(async()=>button.click());
   expect(host.querySelector("main.public-data-workspace > .public-attribution-wrap > .public-data-attribution")).toBe(attribution);
   expect(host.querySelector(".market-strip-wrap")).toBeNull();
   expect(attribution?.textContent).toContain("ODbL 1.0");
   expect(attribution?.querySelector(`a[href="/api/publication/aircraft/download/${batch}"]`)).not.toBeNull();
   expect(host.querySelector("canvas")).toBe(canvas);
  }
  expect(sockets).not.toHaveBeenCalled();
  expect(new Set(requested())).toEqual(new Set(["/api/config","/api/status","/api/publication/aircraft"]));
 });
 it("loads only the dedicated NASA dataset and removes map pixels on request failure",async()=>{
  let unavailable=false;
  const data={source:"nasa_firms_noaa20",status:"fresh",last_attempt_status:"ok",published_at:"2026-11-05T20:00:00Z",batch_id:"a".repeat(64),source_rows:20,regional_rows:2,eligible_count:1,displayed_count:1,minimum_frp_mw:10,hotspots:[{id:"b".repeat(64),source_row_sha256:"c".repeat(64),satellite:"NOAA-20",instrument:"VIIRS",confidence_label:"nominal",lat:29,lon:44,frp:25,ts:"2026-11-05T19:00:00Z"}]};
  vi.mocked(apiFetch).mockImplementation(async input=>String(input).endsWith("/config")?Response.json({...publicConfig,public_observations_enabled:true,public_reports_enabled:true}):String(input).includes("/publication/observations")?(unavailable?new Response("failed",{status:503}):Response.json(data)):Response.json({...publicConfig,mode:"public_read_only"}));
  await act(async()=>root.render(<App/>));
  expect(host.textContent).toContain("Thermal observations available");
  expect(host.querySelector('[data-thermal-count="1"]')).not.toBeNull();
  expect(new Set(requested())).toEqual(new Set(["/api/config","/api/status","/api/publication/observations"]));
  expect(sockets).not.toHaveBeenCalled();
  unavailable=true;await act(async()=>vi.advanceTimersByTimeAsync(65000));
  expect(host.textContent).toContain("Publication unavailable");
  expect(host.querySelector('[data-thermal-count="0"]')).not.toBeNull();
 });
 it("waits for bootstrap before private or data requests, then stays idle when publication is withheld",async()=>{
  let resolveConfig!:(response:Response)=>void;
  vi.mocked(apiFetch).mockImplementation(async input=>String(input).endsWith("/config")?new Promise<Response>(resolve=>{resolveConfig=resolve;}):Response.json({mode:"public_read_only"}));
  await act(async()=>root.render(<App/>));
  await act(async()=>vi.advanceTimersByTimeAsync(65000));
  expect(new Set(requested())).toEqual(new Set(["/api/config","/api/status"]));
  expect(sockets).not.toHaveBeenCalled();
  expect(host.textContent).not.toContain("Settings");
  await act(async()=>resolveConfig(Response.json(publicConfig)));
  await act(async()=>vi.advanceTimersByTimeAsync(180000));
  expect(new Set(requested())).toEqual(new Set(["/api/config","/api/status"]));
  expect(sockets).not.toHaveBeenCalled();
  expect(host.querySelector("canvas")).not.toBeNull();
  expect(host.querySelector('[data-read-only="true"]')).not.toBeNull();
  expect([...host.querySelectorAll("button")].some(button=>button.textContent==="Settings")).toBe(false);
  expect(host.textContent).toContain("Reports withheld");
  expect(host.textContent).toContain("No live coverage is claimed");
 });

 it("keeps Media and Brief as truthful publication states without fetching operator archives",async()=>{
  await act(async()=>root.render(<App/>));
  const canvas=host.querySelector("canvas");
  for(const [name,message] of [["Media","Media is not published"],["Brief","Briefings are not published"]]){
   const button=[...host.querySelectorAll<HTMLButtonElement>(".view-tab-group button")].find(node=>node.textContent===name)!;
   await act(async()=>button.click());
   expect(host.textContent).toContain(message);
   expect(host.querySelector("canvas")).toBe(canvas);
   expect(host.querySelector(".workspace-subnav")).toBeNull();
  }
  await act(async()=>vi.advanceTimersByTimeAsync(180000));
  expect(new Set(requested())).toEqual(new Set(["/api/config","/api/status"]));
  expect(sockets).not.toHaveBeenCalled();
  expect(host.querySelector(".header-costs")).toBeNull();
  expect(host.querySelector(".public-attribution-wrap")).toBeNull();
  expect(host.querySelector("main.public-data-workspace")).not.toBeNull();
 });

 it("fails closed when bootstrap fails instead of requesting operator APIs",async()=>{
  vi.mocked(apiFetch).mockResolvedValue(new Response("unavailable",{status:503}));
  await act(async()=>root.render(<App/>));
  await act(async()=>vi.advanceTimersByTimeAsync(90000));
  expect(new Set(requested())).toEqual(new Set(["/api/config","/api/status"]));
  expect(sockets).not.toHaveBeenCalled();
  expect(host.textContent).toContain("Backend unavailable");
  expect(host.querySelector("canvas")).not.toBeNull();
 });
});
