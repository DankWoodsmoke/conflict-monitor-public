import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import App from "./App";
import {apiFetch} from "./lib/api";
import {buildShowcase} from "./lib/showcase";
import {useEventStream} from "./hooks/useEventStream";

vi.mock("./components/CesiumView",()=>({CesiumView:()=> <div className="earth-canvas"><canvas/>Synthetic renderer fixture</div>}));
vi.mock("./hooks/useEventStream",()=>({useEventStream:vi.fn(()=>({events:[],isConnected:false,loadFullHistory:vi.fn(),historyStatus:"idle",recoveryStatus:"idle",historyTruncated:false,historyStart:null}))}));
vi.mock("./hooks/useTracking",()=>({useTracking:()=>({aircraft:[],vessels:[],jammingZones:[],loadingSnapshots:false,snapshotAt:null})}));
vi.mock("./lib/api",()=>({apiFetch:vi.fn(async()=>Response.json({configured:false,enabled:false,feeds:[],tickers:[],hotspots:[]}))}));
let host:HTMLDivElement,root:Root;
beforeEach(()=>{vi.mocked(useEventStream).mockReturnValue({events:[],isConnected:false,loadFullHistory:vi.fn(),historyStatus:"idle",recoveryStatus:"idle",historyTruncated:false,historyStart:null} as any);vi.mocked(apiFetch).mockImplementation(async()=>Response.json({configured:false,enabled:false,feeds:[],tickers:[],hotspots:[]}));(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;localStorage.setItem("cm_seen_methods_v2","1");window.history.replaceState(null,"","/?view=earth");host=document.createElement("div");document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();localStorage.clear();vi.restoreAllMocks();});
const brief={id:1,trigger:"source_digest",headline:"Synthetic source compilation",escalation_level:"UNASSESSED",escalation_score:null,generated_at:new Date().toISOString(),events_analyzed:1};
const source={...buildShowcase(Date.now()).events[0],id:123,lat:0,lon:0,timestamp:"invalid",source:"rss_fixture",event_type:"unclassified",severity:0,confirmed_networks:"SATELLITE",source_url:"javascript:alert(1)",summary:"Synthetic citation fixture"};
function briefResponses(recording=false){
 vi.mocked(apiFetch).mockImplementation(async(input)=>{const url=String(input);return Response.json(url.includes("/config")?{video_generation_enabled:recording}:url.includes("/videos/manifest")?{"1":{url:"/videos/synthetic-fixture.mp4",generated_at:brief.generated_at}}:url.includes("/sitreps/?")?[brief]:url.endsWith("/events")?[source]:url.includes("/sitreps/")?{sitrep:brief}:{});});
 window.history.replaceState(null,"","/?view=sitrep");
}
describe("application landmarks",()=>{
 it("groups Earth, markets, report feed and timeline in one named native main landmark",async()=>{
  await act(async()=>root.render(<App/>));
  const main=host.querySelector('main[aria-label="Conflict monitoring workspace"]');
  expect(host.querySelectorAll("main")).toHaveLength(1);
  for(const selector of [".earth-stage",".earth-canvas",".market-strip-wrap",".sidebar-feed",".timeline-wrap"])expect(main?.querySelector(selector),selector).not.toBeNull();
 });
 it("keeps modal title headings and close controls without exposing dialog headers as global banners",async()=>{
  await act(async()=>root.render(<App/>));
  for(const [button,title] of [["Settings","Earth & data"],["Sources & health","Sources & health"],["About","Evidence in context."]]){
   const trigger=button==="About"?host.querySelector<HTMLButtonElement>('[aria-label="Methods and evidence limitations"]'):[...host.querySelectorAll("button")].find(node=>node.textContent===button);
   expect(trigger).toBeTruthy();await act(async()=>trigger!.click());
   const dialog=host.querySelector('[role="dialog"]')!;
   expect(dialog.querySelector("header")?.getAttribute("role")).toBe("presentation");expect(dialog.querySelector("h1")?.textContent).toBe(title);expect(dialog.querySelector('header button[aria-label^="Close"]')).not.toBeNull();
   await act(async()=>window.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"})));expect(host.querySelector('[role="dialog"]')).toBeNull();
  }
 });
 it("keeps zero-coordinate context links, rejects unsafe citations and does not infer sensor provenance from network tags",async()=>{
  briefResponses();await act(async()=>root.render(<App/>));
  expect(host.querySelector('a[href^="javascript:"]')).toBeNull();expect(host.textContent).not.toContain("SENSOR REPORTS");
  expect(host.querySelector('a[href*="maps/@0.00000,0.00000"]')).not.toBeNull();expect(host.querySelector('a[href*="worldview.earthdata"]')).toBeNull();
  expect(host.textContent).toContain("SOURCE BRIEFING · TEXT ONLY");expect(host.textContent).not.toContain("TRIGGERS");expect(host.textContent).toContain("Time unknown");
 });
 it("opens an expanded source digest with trapped focus, closes only the overlay on Escape and restores its opener and exact canvas",async()=>{
  briefResponses();vi.spyOn(HTMLElement.prototype,"getClientRects").mockReturnValue([{width:100,height:30}] as any);
  await act(async()=>root.render(<App/>));const canvas=host.querySelector("canvas"),opener=[...host.querySelectorAll("button")].find(n=>n.textContent?.includes("OPEN SOURCE BRIEFING"))!;opener.focus();
  await act(async()=>opener.click());const dialog=host.querySelector<HTMLDivElement>('[role="dialog"]')!;
  expect(dialog.getAttribute("aria-modal")).toBe("true");expect(document.activeElement).toBe(dialog.querySelector('[data-modal-close]'));expect(opener.closest("[inert]")).not.toBeNull();
  const buttons=dialog.querySelectorAll<HTMLButtonElement>("button"),last=buttons[buttons.length-1];last.focus();await act(async()=>window.dispatchEvent(new KeyboardEvent("keydown",{key:"Tab",cancelable:true})));expect(document.activeElement).toBe(buttons[0]);
  expect(dialog.textContent).toContain("REPORTS COMPILED");expect(dialog.textContent).not.toContain("EVENTS ANALYZED");
  await act(async()=>window.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",cancelable:true})));
  expect(host.querySelector('[role="dialog"]')).toBeNull();expect(host.querySelector(".workspace-panel")).not.toBeNull();expect(document.activeElement).toBe(opener);expect(opener.closest("[inert]")).toBeNull();expect(host.querySelector("canvas")).toBe(canvas);
 });
 it("offers keyboard-accessible recorded playback with the same modal Escape/focus behavior",async()=>{
  briefResponses(true);await act(async()=>root.render(<App/>));const opener=host.querySelector<HTMLButtonElement>('[aria-label="Play recording for briefing 1"]')!;expect(opener).not.toBeNull();opener.focus();
  await act(async()=>opener.click());const dialog=host.querySelector('[role="dialog"][aria-label="Recorded briefing video playback"]');expect(dialog?.querySelector("video[controls]")).not.toBeNull();expect(document.activeElement).toBe(dialog?.querySelector('[data-modal-close]'));
  await act(async()=>window.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",cancelable:true})));expect(host.querySelector('[role="dialog"]')).toBeNull();expect(host.querySelector(".workspace-panel")).not.toBeNull();expect(document.activeElement).toBe(opener);
 });
 it("does not attach a late response from an earlier briefing to the currently selected source references",async()=>{
  const second={...brief,id:2,headline:"Second synthetic compilation"};let finishFirst!:(value:Response)=>void;
  vi.mocked(apiFetch).mockImplementation(async(input)=>{const url=String(input);if(url.endsWith('/sitreps/1/events'))return new Promise<Response>(resolve=>{finishFirst=resolve;});return Response.json(url.includes('/sitreps/?')?[brief,second]:url.endsWith('/sitreps/2/events')?[{...source,summary:"Second source fixture"}]:url.endsWith('/sitreps/2')?{sitrep:second}:url.endsWith('/sitreps/latest')?{sitrep:brief}:{});});window.history.replaceState(null,"","/?view=sitrep");
  await act(async()=>root.render(<App/>));await act(async()=>[...host.querySelectorAll<HTMLButtonElement>('.sitrep-history-card')].find(n=>n.textContent?.includes(second.headline))!.click());
  await act(async()=>finishFirst(Response.json([{...source,summary:"Obsolete first source fixture"}])));expect(host.textContent).toContain("Second source fixture");expect(host.textContent).not.toContain("Obsolete first source fixture");
 });
 it("keeps native keyboard source filtering effective for ALL history and preserves other source families",async()=>{
  const base=buildShowcase(Date.now()).events[0];vi.mocked(useEventStream).mockReturnValue({events:[{...base,source:"rss_fixture",summary:"RSS visible fixture"},{...base,id:999,source:"unknown_provider",summary:"Other visible fixture"}],isConnected:false,loadFullHistory:vi.fn(),historyStatus:"idle",recoveryStatus:"idle",historyTruncated:false,historyStart:null} as any);
  await act(async()=>root.render(<App/>));await act(async()=>[...host.querySelectorAll("button")].find(n=>n.textContent==="ALL")!.click());
  const toggle=host.querySelector<HTMLButtonElement>('[title="Filter by source type"]')!;await act(async()=>toggle.click());const picker=host.querySelector('[role="group"][aria-label="Source categories"]')!,rss=[...picker.querySelectorAll("label")].find(n=>n.textContent?.includes("RSS news feeds"))!.querySelector<HTMLInputElement>("input")!;
  expect(rss.style.display).not.toBe("none");rss.focus();expect(document.activeElement).toBe(rss);await act(async()=>rss.click());
  expect(host.querySelector('.sidebar-feed')?.textContent).not.toContain("RSS visible fixture");expect(host.querySelector('.sidebar-feed')?.textContent).toContain("Other visible fixture");
  await act(async()=>rss.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true,cancelable:true})));expect(host.querySelector('[aria-label="Source categories"]')).toBeNull();expect(document.activeElement).toBe(toggle);
 });
 it("uses automatic eligible selection for local tools rather than implicitly selecting recent Telegram rows",async()=>{
  const base=buildShowcase(Date.now()).events[0];vi.mocked(useEventStream).mockReturnValue({events:[{...base,source:'telegram'}],isConnected:false,loadFullHistory:vi.fn(),historyStatus:'idle',recoveryStatus:'idle',historyTruncated:false,historyStart:null} as any);
  window.history.replaceState(null,'','/?view=sitrep');await act(async()=>root.render(<App/>));await act(async()=>[...host.querySelectorAll('button')].find(node=>node.textContent==='Local analysis')!.click());
  expect(host.querySelector('.local-briefing-panel')?.textContent).toContain('Latest eligible reports · up to 4');expect(host.querySelector('.local-briefing-panel')?.textContent).not.toContain('1 selected report');expect(vi.mocked(apiFetch).mock.calls.every(([,init])=>init?.method!=='POST')).toBe(true);
 });
});
