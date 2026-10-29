import {act,useEffect} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {LiveFeed} from "./LiveFeed";
import {MarketStrip} from "./MarketStrip";
import {MediaFrame} from "./MediaFrame";
import {SourceStatus} from "./SourceStatus";
import {useArrayPoll} from "../hooks/useArrayPoll";
import {averageSeverity,severityLabel,reportSourceKind} from "../lib/events";
import {briefIndexLabel,isSourceDigest} from "../lib/brief";
import {buildShowcase} from "../lib/showcase";
import {apiFetch} from "../lib/api";

vi.mock("../lib/api",()=>({apiFetch:vi.fn()}));
const fetchMock=vi.mocked(apiFetch);let host:HTMLDivElement,root:Root;
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-29T03:00:00Z"));host=document.createElement("div");document.body.append(host);root=createRoot(host);fetchMock.mockReset();});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();});

describe("free report integrity",()=>{
 it("names the severity reset ALL and restores unscored records after a scored threshold",async()=>{
  const base=buildShowcase(Date.now()).events[0],unscored={...base,id:1,severity:0,summary:"Unscored reset fixture"},scored={...base,id:2,severity:7,summary:"Scored threshold fixture"};
  await act(async()=>root.render(<LiveFeed events={[unscored,scored]}/>));
  await act(async()=>[...host.querySelectorAll("button")].find(button=>button.textContent==="FILTER")!.click());
  const reset=host.querySelector<HTMLButtonElement>('[aria-label="All severities, including unscored"]')!;
  expect(reset.textContent).toBe("ALL");expect(reset.title).toBe("All severities, including unscored");expect(reset.getAttribute("aria-pressed")).toBe("true");
  await act(async()=>host.querySelector<HTMLButtonElement>('[aria-label="Scored severity 5/10 and above"]')!.click());
  expect(host.querySelectorAll('.intel-card')).toHaveLength(1);expect(host.textContent).not.toContain(unscored.summary);
  await act(async()=>reset.click());expect(host.querySelectorAll('.intel-card')).toHaveLength(2);expect(host.textContent).toContain(unscored.summary);
 });
 it("uses explicit sensor provenance and keeps unknown source families distinct from RSS",async()=>{
  const base=buildShowcase(Date.now()).events[0],event={...base,source:"unknown_provider",event_type:"unclassified" as const,severity:0,confirmed_networks:"SATELLITE",evidence:{...base.evidence!,unique_source_count:1},report_count:1};
  await act(async()=>root.render(<LiveFeed events={[event]}/>));expect(host.querySelector('.intel-card')?.textContent).not.toMatch(/SAT|SENSOR TAG/);expect(host.textContent).toContain("OTHER");
  await act(async()=>root.render(<LiveFeed events={[{...event,source:"satellite_firms",event_type:"thermal_anomaly"}]}/>));expect(host.querySelector('.intel-card')?.textContent).toContain("SAT");
 });
 it.each(["𝕏","✓ MULTI-REPORT ONLY"])("attributes an empty feed to active filters (%s)",async(label)=>{
  const base=buildShowcase(Date.now()).events[0];const event={...base,source:"rss_fixture",evidence:{...base.evidence!,status:"reported" as const,unique_source_count:1}};
  await act(async()=>root.render(<LiveFeed events={[event]}/>));
  await act(async()=>[...host.querySelectorAll("button")].find(button=>button.textContent==="FILTER")!.click());
  await act(async()=>[...host.querySelectorAll("button")].find(button=>button.textContent===label)!.click());
  expect(host.textContent).toContain("No reports match active filters");expect(host.textContent).not.toContain("No reports in this window");
 });
 it("labels and counts the entire loaded source mix independently from the visible time window",async()=>{
  const base=buildShowcase(Date.now()).events[0],all=Array.from({length:205},(_,i)=>({...base,id:i+1,source:"rss_fixture"}));
  await act(async()=>root.render(<LiveFeed events={all.slice(0,1)} allEvents={all}/>));
  const mix=host.querySelector('[title^="Up to three largest source categories"]');
  expect(mix?.textContent).toContain("ALL LOADED");expect(mix?.textContent?.replace(/\s/g," ")).toContain("RSS 205");
  expect(host.querySelectorAll('.intel-card')).toHaveLength(1);
 });
 it("shows unclassified source reports without inventing impact or a map position",async()=>{
  const event={...buildShowcase(Date.now()).events[0],event_type:"unclassified" as const,severity:0,classification_status:"not_requested" as const,lat:null,lon:null,location_name:"",summary:"Exact original publisher headline",raw_text:"Preserved source text"};
  await act(async()=>root.render(<LiveFeed events={[event]} onEventClick={()=>{}}/>));
  expect(host.textContent).toContain("Exact original publisher headline");expect(host.textContent).toContain("UNSCORED");expect(host.textContent).toContain("Location unresolved");expect(host.textContent).not.toContain("0/10");expect(host.querySelector('button[aria-label^="Locate report:"]')).toBeNull();
  expect(host.textContent).toContain("Source report · model not requested");
 });
 it("never turns unknown brief severity into a 50/100 or zero-risk estimate",()=>{
  expect(briefIndexLabel({escalation_score:null})).toBe("UNASSESSED");expect(isSourceDigest({trigger:"source_digest"})).toBe(true);
  const events=buildShowcase(Date.now()).events;
  expect(averageSeverity([{...events[0],severity:0}])).toBeNull();
  expect(averageSeverity([{...events[0],severity:8},{...events[1],severity:0}])).toBe(8);expect(severityLabel({severity:0})).toBe("UNSCORED");
 });
 it("displays fetched age and publication age separately in provider status",async()=>{
  fetchMock.mockResolvedValue(Response.json({mode:"live",news_feeds:{mode:"reports",enabled:true,feeds:[{source:"publisher",status:"ok",cache_age_seconds:20,publication_age_seconds:172800,publication_stale:true,published_items:2,error_type:null}]}}));
  await act(async()=>root.render(<SourceStatus fallback="Connecting"/>));
  await act(async()=>host.querySelector<HTMLButtonElement>('button')!.click());
  expect(host.textContent).toContain("Fetch age20s");expect(host.textContent).toContain("Newest source publication age2d · old publication");
  await act(async()=>window.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"})));expect(host.querySelector('[role="dialog"]')).toBeNull();
 });
});

describe("Telegram coverage receipts",()=>{
 it("preserves separate clocks and bounded history rather than implying a complete archive",async()=>{
  fetchMock.mockResolvedValue(Response.json({mode:"live",telegram:{enabled:true,status:"ok",mode:"reports",cache_age_seconds:30,publication_age_seconds:7200,startup_limit_per_channel:3,channels:{public_fixture:{status:"ok",processed:3,history_complete:false,startup_or_cycle_limit:3}}}}));
  await act(async()=>root.render(<SourceStatus fallback="Connecting"/>));await act(async()=>host.querySelector<HTMLButtonElement>("button")!.click());
  expect(host.textContent).toContain("Telegram collectionok");expect(host.textContent).toContain("Fetch age30s");expect(host.textContent).toContain("Newest source publication age2h");expect(host.textContent).toContain("@public_fixture");expect(host.textContent).toContain("Incomplete / bounded");expect(host.textContent).not.toContain("Declared complete");
 });
});

describe("live cache boundaries",()=>{
 it("expires aircraft after repeated backend failure instead of showing them forever",async()=>{
  let latest:any;
  function Harness(){const result=useArrayPoll<{id:number}>("/fixture",1000,2000);useEffect(()=>{latest=result;},[result]);return null;}
  fetchMock.mockResolvedValueOnce(Response.json([{id:1}])).mockRejectedValue(new Error("offline"));
  await act(async()=>root.render(<Harness/>));expect(latest.data).toEqual([{id:1}]);
  await act(async()=>vi.advanceTimersByTimeAsync(1000));expect(latest.status.state).toBe("stale");expect(latest.data).toHaveLength(1);
  await act(async()=>vi.advanceTimersByTimeAsync(1000));expect(latest.data).toEqual([]);expect(latest.status.state).toBe("stale");
 });
 it("serializes polling while a provider request is still pending",async()=>{
  let release!:(r:Response)=>void;fetchMock.mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
  function Harness(){useArrayPoll("/fixture",1000,2000);return null;}
  await act(async()=>root.render(<Harness/>));await act(async()=>vi.advanceTimersByTimeAsync(5000));expect(fetchMock).toHaveBeenCalledTimes(1);
  await act(async()=>release(Response.json([])));await act(async()=>vi.advanceTimersByTimeAsync(1000));expect(fetchMock).toHaveBeenCalledTimes(2);
 });
 it("rejects malformed snapshots and never substitutes synthetic content",async()=>{
  let latest:any;fetchMock.mockResolvedValue(Response.json({states:[{id:1}]}));
  function Harness(){const value=useArrayPoll("/fixture",1000,2000);useEffect(()=>{latest=value;},[value]);return null;}
  await act(async()=>root.render(<Harness/>));expect(latest.data).toEqual([]);expect(latest.status.state).toBe("unavailable");
 });
});


describe("live provider presentation",()=>{
 it("describes regional aircraft coverage without implying a global feed",async()=>{
  fetchMock.mockResolvedValue(Response.json({mode:"live",aircraft:{status:"ok",coverage:{kind:"regional_circles",radius_nm:250,minimum_request_interval_seconds:15,nominal_revisit_seconds:60,circles:[{id:"gulf",label:"Gulf",lat:25,lon:52,radius_nm:250}]},regions:[{id:"gulf",label:"Gulf",status:"ok",cache_age_seconds:25}]}}));
  await act(async()=>root.render(<SourceStatus fallback="Connecting"/>));await act(async()=>host.querySelector<HTMLButtonElement>('button')!.click());
  expect(host.textContent).toContain("1 selected regional circles · 250 nautical-mile radius");expect(host.textContent).toContain("One request per 15 seconds");expect(host.textContent).toContain("nominal regional revisit 60 seconds");expect(host.textContent).toContain("surface projections");
 });
 it("sends the origin referrer required by YouTube even if a caller supplies a suppressing policy",async()=>{
  await act(async()=>root.render(<MediaFrame src="https://www.youtube.com/embed/fixture" title="YouTube fixture" referrerPolicy="no-referrer"/>));
  expect(host.querySelector("iframe")).toBeNull();
  await act(async()=>host.querySelector<HTMLButtonElement>("button")!.click());
  expect(host.querySelector('iframe')?.getAttribute('referrerpolicy')).toBe("strict-origin-when-cross-origin");
 });
 it("does not call a satellite sensor an RSS publisher",()=>{
  expect(reportSourceKind({source:"satellite_firms",event_type:"thermal_anomaly"})).toBe("sensor");
  expect(reportSourceKind({source:"rss_aljazeera",event_type:"unclassified"})).toBe("rss");
 });
 it("shows an unavailable market result instead of an endless loading state",async()=>{
  fetchMock.mockRejectedValue(new Error("provider offline"));
  await act(async()=>root.render(<MarketStrip/>));expect(host.textContent).toContain("Market data unavailable");expect(host.textContent).not.toContain("Loading provider snapshot");
 });
 it("distinguishes disabled markets from an upstream failure",async()=>{
  fetchMock.mockResolvedValue(Response.json({data:[],status:"disabled",stale:true}));
  await act(async()=>root.render(<MarketStrip/>));expect(host.textContent).toContain("Market provider disabled");
 });
 it("does not interpret an iframe load event as a live-stream qualification",async()=>{
  await act(async()=>root.render(<MediaFrame src="https://example.org/embed" title="External fixture"/>));
  expect(host.querySelector("iframe")).toBeNull();
  await act(async()=>host.querySelector<HTMLButtonElement>("button")!.click());
  const frame=host.querySelector("iframe")!;expect(frame).not.toBeNull();
  await act(async()=>frame.dispatchEvent(new Event("load")));
  expect(host.textContent).toContain("playback and live status unverified");
 });
});
