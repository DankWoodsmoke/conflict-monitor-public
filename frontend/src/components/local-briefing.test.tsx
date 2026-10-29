import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {LocalBriefingPanel,videoSource} from "./LocalBriefingPanel";
import {apiFetch} from "../lib/api";

vi.mock("../lib/api",()=>({apiFetch:vi.fn()}));
vi.mock("../lib/runtime",()=>({SHOWCASE:false,API_BASE:"/api"}));
const fetchMock=vi.mocked(apiFetch);
const status={local_ai:{enabled:true,state:"ready",model:"stock-fixture"},video:{enabled:true,state:"ready",voice_configured:true}};
const report={id:7,source:"Fixture publisher",published_at:"2026-10-29T02:00:00Z",source_url:"https://example.org/source",
 text:"The ministry denied a strike in Aden.",headline:"Exact fixture headline",relevance:"relevant",stance:"denied",
 mentions:{place_mentions:[{text:"Aden",start:31,end:35,status:"source_mention_not_event_location"}]}};
const analysis={status:"available",generated_at:"2026-10-29T03:00:00Z",reports:[report],semantic_entailment:"unreviewed"};
const video={status:"available",filename:"a".repeat(32)+".mp4",generated_at:"2026-10-29T03:00:00Z",duration_seconds:30,sources:[report],sha256:"b".repeat(64)};
let host:HTMLDivElement,root:Root,mounted:boolean;
function response(input:RequestInfo|URL,init?:RequestInit):Promise<Response>{
 const u=String(input);return Promise.resolve(Response.json(init?.method==="POST"?{status:"queued"}:u.endsWith("/status")?status:u.endsWith("/latest")?analysis:video,{status:init?.method==="POST"?202:200}));
}
function button(text:string){return [...host.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent===text)!;}
beforeEach(()=>{
 (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-29T03:10:00Z"));
 fetchMock.mockReset().mockImplementation(response);localStorage.clear();sessionStorage.clear();
 host=document.createElement("div");document.body.append(host);root=createRoot(host);mounted=true;
});
afterEach(async()=>{if(mounted)await act(async()=>root.unmount());host.remove();vi.useRealTimers();});

describe("local briefing operator workflow",()=>{
 it("explains permission rejection separately from network/model failure while retaining an allowed last result",async()=>{
  fetchMock.mockImplementation((input,init)=>String(input).endsWith('/status')?Promise.resolve(Response.json({...status,local_ai:{...status.local_ai,state:'failed',error_type:'SourcePermissionRequired'}})):response(input,init));
  await act(async()=>root.render(<LocalBriefingPanel/>));expect(host.textContent).toContain('Source permission required · no AI or speech work was started');expect(host.textContent).toContain('Automatic selection skips them');expect(host.textContent).toContain('Other source rights still need review');expect(host.textContent).toContain(report.headline);expect(host.textContent).not.toContain('Failed (SourcePermissionRequired)');expect(fetchMock.mock.calls.every(([,init])=>!init?.method)).toBe(true);
 });
 it("withholds a restricted analysis without hiding an eligible video or treating the policy as HTTP failure",async()=>{
  fetchMock.mockImplementation((input,init)=>String(input).endsWith('/latest')?Promise.resolve(Response.json({detail:{code:'SourcePermissionRequired'}},{status:403})):response(input,init));
  await act(async()=>root.render(<LocalBriefingPanel/>));expect(host.textContent).toContain('this analysis is withheld pending eligibility review');expect(host.textContent).not.toContain(report.headline);expect(host.querySelector('video[controls]')).not.toBeNull();expect(host.textContent).not.toContain('HTTP 403');
 });
 it("withholds restricted video while preserving eligible analysis and never loads the forbidden file",async()=>{
  fetchMock.mockImplementation((input,init)=>String(input).endsWith('/video/manifest')?Promise.resolve(Response.json({detail:{code:'SourcePermissionRequired'}},{status:403})):response(input,init));
  await act(async()=>root.render(<LocalBriefingPanel/>));expect(host.textContent).toContain('this narrated video is withheld pending eligibility review');expect(host.querySelector('video')).toBeNull();expect(host.textContent).toContain(report.headline);expect(fetchMock.mock.calls.every(([,init])=>!init?.method)).toBe(true);
 });
 it("only reads on viewing, preserving the exact report and uncertainty labels",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel/>));
  expect(fetchMock.mock.calls.every(([,init])=>!init?.method)).toBe(true);
  expect(host.textContent).toContain(report.text);expect(host.textContent).toContain("Linguistic stance: denied");
  expect(host.textContent).toContain("not verified incident locations");
  expect(host.querySelector('video')?.hasAttribute("controls")).toBe(true);
  expect(host.querySelector('video')?.hasAttribute("autoplay")).toBe(false);
 });
 it("asks for explicit operator access without sending an unauthenticated POST",async()=>{
  const configure=vi.fn();await act(async()=>root.render(<LocalBriefingPanel onConfigureOperator={configure}/>));
  await act(async()=>button("Analyze source reports").click());
  expect(configure).toHaveBeenCalledOnce();expect(fetchMock.mock.calls.filter(([,init])=>init?.method==="POST")).toHaveLength(0);
 });
 it("sends the memory-only access key solely in the explicit request header",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel eventIds={[7,8,7]} operatorKey="fixture-operator-memory-only"/>));
  await act(async()=>button("Analyze source reports").click());
  const calls=fetchMock.mock.calls.filter(([,init])=>init?.method==="POST");expect(calls).toHaveLength(1);
  expect(calls[0][0]).toBe("/api/briefing/analyze");expect(calls[0][1]?.headers).toEqual({"Content-Type":"application/json","X-Admin-Key":"fixture-operator-memory-only"});
  expect(JSON.parse(String(calls[0][1]?.body))).toEqual({event_ids:[7,8]});
  expect(JSON.stringify([...Object.keys(localStorage),...Object.keys(sessionStorage)])).not.toContain("operator");
  expect(host.textContent).not.toContain("fixture-operator-memory-only");expect(host.textContent).toContain("Analysis queued locally");
 });
 it.each([[1,2,3,4,5,6,7,8,9],[0],[-1],[1.5]].map(ids=>({ids})))("rejects oversized or invalid selections without silent truncation ($ids)",async({ids})=>{
  await act(async()=>root.render(<LocalBriefingPanel eventIds={ids} operatorKey="fixture-access"/>));
  expect(button("Analyze source reports").disabled).toBe(true);expect(host.textContent).toContain("Choose at most 8 valid reports");
 });
 it("bounds video selection independently and never substitutes another file URL",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel eventIds={[1,2,3,4,5]}/>));
  expect(button("Make narrated briefing").disabled).toBe(true);expect(button("Analyze source reports").disabled).toBe(false);
  expect(videoSource({...video,url:"https://attacker.invalid/video.mp4"} as any)).toBe(`/api/briefing/video/${video.filename}`);
  for(const filename of ["../private.mp4","https://attacker.invalid/video.mp4","a.mp4",""])
   expect(videoSource({...video,filename})).toBe("");
 });
 it("renders hostile source text as text and labels stale artifacts",async()=>{
  fetchMock.mockImplementation((input,init)=>String(input).endsWith("/latest")?Promise.resolve(Response.json({...analysis,stale:true,reports:[{...report,headline:"<img src=x onerror=alert(1)>",source_url:"javascript:alert(1)"}]})):response(input,init));
  await act(async()=>root.render(<LocalBriefingPanel mode="analysis"/>));
  expect(host.querySelector("img")).toBeNull();expect(host.textContent).toContain("<img src=x onerror=alert(1)>");
  expect(host.textContent).toContain("STALE RESULT");expect(host.textContent).toContain("Source link unavailable");
 });
 it("does not turn malformed model output or HTTP failure into a demonstration",async()=>{
  fetchMock.mockImplementation((input,init)=>String(input).endsWith("/latest")?Promise.resolve(Response.json({...analysis,reports:[{...report,id:0}]})):response(input,init));
  await act(async()=>root.render(<LocalBriefingPanel mode="analysis"/>));
  expect(host.textContent).toContain("Invalid analysis reports");expect(host.textContent).not.toContain("Exact fixture headline");
  fetchMock.mockResolvedValue(Response.json({}, {status:503}));await act(async()=>vi.advanceTimersByTimeAsync(15000));
  expect(host.textContent).toContain("HTTP 503");expect(fetchMock.mock.calls.some(([,init])=>init?.method==="POST")).toBe(false);
 });
 it("keeps read polling serial and aborts every owned request on unmount",async()=>{
  let release!:(response:Response)=>void;const signals:AbortSignal[]=[];
  fetchMock.mockImplementation((input,init)=>{if(init?.signal)signals.push(init.signal);return String(input).endsWith("/status")?new Promise(resolve=>{release=resolve;}):response(input,init);});
  await act(async()=>root.render(<LocalBriefingPanel/>));await act(async()=>vi.advanceTimersByTimeAsync(45000));
  expect(fetchMock).toHaveBeenCalledTimes(3);
  await act(async()=>root.unmount());mounted=false;expect(signals.every(signal=>signal.aborted)).toBe(true);
  await act(async()=>{release(Response.json(status));await vi.advanceTimersByTimeAsync(45000);});
  expect(fetchMock).toHaveBeenCalledTimes(3);expect(host.textContent).toBe("");
 });
 it("reports video playback failure without interpreting metadata receipt as playback proof",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel mode="video"/>));
  await act(async()=>host.querySelector("video")!.dispatchEvent(new Event("error")));
  expect(host.textContent).toContain("completed video could not be played");
 });
});
