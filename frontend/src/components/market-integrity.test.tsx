import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {MarketStrip,validateMarketSnapshot} from "./MarketStrip";
import {apiFetch} from "../lib/api";

vi.mock("../lib/api",()=>({apiFetch:vi.fn()}));
vi.mock("../lib/runtime",()=>({API_BASE:"/api"}));
const request=vi.mocked(apiFetch),POLL=300000;
function snapshot(){return {stale:false,cached_ago:4,status:"cached",data:[{symbol:"BZ=F",name:"BRENT",unit:"$/bbl",category:"oil",price:72.15,change_pct:1.23,change_abs:0.88,market_state:"unknown",observation_time:null,source:"Yahoo Finance via yfinance"}]};}
let host:HTMLDivElement,root:Root,mounted:boolean;
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-30T18:00:00Z"));request.mockReset().mockResolvedValue(Response.json(snapshot()));host=document.createElement("div");document.body.append(host);root=createRoot(host);mounted=true;});
afterEach(async()=>{if(mounted)await act(async()=>root.unmount());host.remove();vi.useRealTimers();});

describe("provider snapshot metadata",()=>{
 it("keeps unknown quote time separate from current retrieval and visible snapshot status",async()=>{
  await act(async()=>root.render(<MarketStrip/>));expect(host.textContent).toContain("SNAPSHOT · QUOTE TIME UNKNOWN");
  const item=host.querySelector('[tabindex="0"]')!;
  expect(item.getAttribute("title")).toContain("Yahoo Finance via yfinance");expect(item.getAttribute("title")).toContain("unknown; retrieval does not establish quote freshness");
  expect(item.getAttribute("aria-label")).toContain("Quote observation time: unknown");expect(item.getAttribute("aria-label")).toContain("Retrieved 2026-10-30T18:00:00.000Z");
  expect(host.textContent).not.toMatch(/\bLIVE\b/);expect(host.firstElementChild?.getAttribute("style")).toContain("height: 30px");
 });
 it("preserves an older provider quote clock instead of replacing it with retrieval time",async()=>{
  const value=snapshot();value.data[0].observation_time="2026-10-27T15:35:00Z" as any;value.data[0].market_state="CLOSED";
  request.mockResolvedValue(Response.json(value));await act(async()=>root.render(<MarketStrip/>));
  const title=host.querySelector('[tabindex="0"]')!.getAttribute("title");expect(title).toContain("Quote observation time: 2026-10-27T15:35:00Z");expect(title).toContain("Market state: CLOSED");expect(title).toContain("Retrieved: 2026-10-30T18:00:00.000Z");
 });
 it.each(["price","change_pct","change_abs","name","unit","category","market_state","source","time","future","duplicate","stale","age"])("rejects malformed %s without coercing values",kind=>{
  const value:any=snapshot();
  if(["price","change_pct","change_abs"].includes(kind))value.data[0][kind]=Infinity;
  if(["name","unit","category","market_state","source"].includes(kind))value.data[0][kind]={text:"wrong type"};
  if(kind==="time")value.data[0].observation_time="yesterday";
  if(kind==="future")value.data[0].observation_time="2099-01-01T00:00:00Z";
  if(kind==="duplicate")value.data.push({...value.data[0]});
  if(kind==="stale")value.stale="false";
  if(kind==="age")value.cached_ago="4";
  expect(()=>validateMarketSnapshot(value)).toThrow();
 });
 it("preserves missing historical metadata as unknown and never infers a quote clock",()=>{
  const value:any=snapshot();delete value.data[0].source;delete value.data[0].observation_time;
  const checked=validateMarketSnapshot(value);expect(checked.data[0].source).toBe("Source unreported");expect(checked.data[0].observation_time).toBeNull();
 });
});

describe("market snapshot observer lifecycle",()=>{
 it("picks up a warming provider cache after 5 seconds then restores the 5 minute cadence",async()=>{
  request.mockResolvedValueOnce(Response.json({data:[],stale:true,cached_ago:-1,status:"loading"}));
  await act(async()=>root.render(<MarketStrip/>));expect(host.textContent).toContain("Loading provider snapshot");
  await act(async()=>vi.advanceTimersByTimeAsync(4999));expect(request).toHaveBeenCalledTimes(1);
  await act(async()=>vi.advanceTimersByTimeAsync(1));expect(request).toHaveBeenCalledTimes(2);expect(host.textContent).toContain("72.15");
  await act(async()=>vi.advanceTimersByTimeAsync(POLL-1));expect(request).toHaveBeenCalledTimes(2);
  await act(async()=>vi.advanceTimersByTimeAsync(1));expect(request).toHaveBeenCalledTimes(3);
 });
 it("bounds loading retries to 4 checks with increasing delays and never restarts that burst",async()=>{
  request.mockImplementation(async()=>Response.json({data:[],stale:true,cached_ago:-1,status:"loading"}));
  await act(async()=>root.render(<MarketStrip/>));
  for(const [index,delay] of [5000,10000,20000,30000].entries()){
   await act(async()=>vi.advanceTimersByTimeAsync(delay-1));expect(request).toHaveBeenCalledTimes(index+1);
   await act(async()=>vi.advanceTimersByTimeAsync(1));expect(request).toHaveBeenCalledTimes(index+2);
  }
  await act(async()=>vi.advanceTimersByTimeAsync(POLL-1));expect(request).toHaveBeenCalledTimes(5);
  await act(async()=>vi.advanceTimersByTimeAsync(1));expect(request).toHaveBeenCalledTimes(6);
  await act(async()=>vi.advanceTimersByTimeAsync(POLL-1));expect(request).toHaveBeenCalledTimes(6);
  expect(host.textContent).toContain("Loading provider snapshot");
 });
 it("keeps a retained quote snapshot on normal cadence even while backend status is loading",async()=>{
  const value=snapshot();value.status="loading";value.stale=true;value.cached_ago=301;
  request.mockResolvedValueOnce(Response.json(value));await act(async()=>root.render(<MarketStrip/>));
  expect(host.textContent).toContain("72.15");expect(host.textContent).toContain("DELAYED");
  await act(async()=>vi.advanceTimersByTimeAsync(POLL-1));expect(request).toHaveBeenCalledTimes(1);
  await act(async()=>vi.advanceTimersByTimeAsync(1));expect(request).toHaveBeenCalledTimes(2);
 });
 it.each(["disabled","unavailable","cached",undefined])("keeps empty %s responses on normal cadence",async status=>{
  request.mockImplementation(async()=>Response.json({data:[],stale:true,cached_ago:-1,status}));
  await act(async()=>root.render(<MarketStrip/>));await act(async()=>vi.advanceTimersByTimeAsync(POLL-1));
  expect(request).toHaveBeenCalledTimes(1);expect(host.textContent).not.toContain("Loading provider snapshot");
  await act(async()=>vi.advanceTimersByTimeAsync(1));expect(request).toHaveBeenCalledTimes(2);
 });
 it("ends startup retries after a failed short poll without treating failure as loading",async()=>{
  request.mockResolvedValueOnce(Response.json({data:[],stale:true,cached_ago:-1,status:"loading"})).mockRejectedValueOnce(new Error("offline"));
  await act(async()=>root.render(<MarketStrip/>));await act(async()=>vi.advanceTimersByTimeAsync(5000));
  expect(host.textContent).toContain("Market data unavailable");expect(request).toHaveBeenCalledTimes(2);
  await act(async()=>vi.advanceTimersByTimeAsync(POLL-1));expect(request).toHaveBeenCalledTimes(2);
 });
 it("keeps a pending startup check serial and ignores its late result after unmount",async()=>{
  let finish!:(r:Response)=>void;
  request.mockResolvedValueOnce(Response.json({data:[],stale:true,cached_ago:-1,status:"loading"})).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  await act(async()=>root.render(<MarketStrip/>));await act(async()=>vi.advanceTimersByTimeAsync(5000));
  await act(async()=>vi.advanceTimersByTimeAsync(POLL*3));expect(request).toHaveBeenCalledTimes(2);
  const signal=request.mock.calls[1][1]?.signal as AbortSignal;
  await act(async()=>root.unmount());mounted=false;expect(signal.aborted).toBe(true);
  await act(async()=>finish(Response.json(snapshot())));await act(async()=>vi.advanceTimersByTimeAsync(POLL*3));
  expect(request).toHaveBeenCalledTimes(2);expect(host.textContent).toBe("");
 });
 it("cancels a scheduled short loading retry on unmount",async()=>{
  request.mockResolvedValueOnce(Response.json({data:[],stale:true,cached_ago:-1,status:"loading"}));
  await act(async()=>root.render(<MarketStrip/>));await act(async()=>root.unmount());mounted=false;
  await act(async()=>vi.advanceTimersByTimeAsync(POLL));expect(request).toHaveBeenCalledTimes(1);
 });
 it("does not overlap requests, retires owned fetch on unmount and ignores late data",async()=>{
  let finish!:(r:Response)=>void;request.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  await act(async()=>root.render(<MarketStrip/>));await act(async()=>vi.advanceTimersByTimeAsync(POLL*3));expect(request).toHaveBeenCalledTimes(1);
  const signal=request.mock.calls[0][1]?.signal as AbortSignal;await act(async()=>root.unmount());mounted=false;expect(signal.aborted).toBe(true);
  await act(async()=>finish(Response.json(snapshot())));await act(async()=>vi.advanceTimersByTimeAsync(POLL*3));expect(request).toHaveBeenCalledTimes(1);expect(host.textContent).toBe("");
 });
 it("marks cache expiry delayed before a new retrieval can complete",async()=>{
  const value=snapshot();value.cached_ago=299;request.mockResolvedValueOnce(Response.json(value));
  await act(async()=>root.render(<MarketStrip/>));expect(host.textContent).not.toContain("DELAYED");await act(async()=>vi.advanceTimersByTimeAsync(1001));
  expect(host.textContent).toContain("DELAYED");expect(request).toHaveBeenCalledTimes(1);
 });
 it("retains the last valid prices with explicit delay after malformed refresh",async()=>{
  const malformed:any=snapshot();malformed.data[0].price=999;malformed.data[0].change_pct="4.0";
  request.mockResolvedValueOnce(Response.json(snapshot())).mockResolvedValueOnce(Response.json(malformed));
  await act(async()=>root.render(<MarketStrip/>));await act(async()=>vi.advanceTimersByTimeAsync(POLL));
  expect(host.textContent).toContain("72.15");expect(host.textContent).not.toContain("999.00");expect(host.textContent).toContain("DELAYED");
  expect(host.querySelector('[tabindex="0"]')!.getAttribute("aria-label")).toContain("Delayed or unavailable refresh");
 });
 it("clears scheduled poll and cache-expiry timers on unmount",async()=>{
  await act(async()=>root.render(<MarketStrip/>));await act(async()=>root.unmount());mounted=false;
  await act(async()=>vi.advanceTimersByTimeAsync(POLL*6));expect(request).toHaveBeenCalledTimes(1);
 });
});
