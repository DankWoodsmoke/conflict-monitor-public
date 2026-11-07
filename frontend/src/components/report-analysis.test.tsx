import {createHash} from "node:crypto";
import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {ReportAnalysis,validateReportAnalysis} from "./ReportAnalysis";
import type {ConflictEvent} from "../types/event";
import {apiFetch} from "../lib/api";

vi.mock("../lib/api",()=>({apiFetch:vi.fn()}));
vi.mock("../lib/runtime",()=>({SHOWCASE:false,API_BASE:"/api"}));
const request=vi.mocked(apiFetch);
const event={id:17,source:"rss_test",source_url:"https://example.org/report",timestamp:"2026-10-30T12:00:00Z",raw_text:"🛰️ Officials denied an airstrike in Beirut. <img src=x>"} as ConflictEvent;
const sourceHash=(text=event.raw_text)=>createHash("sha256").update(text).digest("hex");
const id="11111111-1111-4111-8111-111111111111";
function queued(){return {job_id:id,event_id:17,source_sha256:sourceHash(),status:"queued",status_url:`/report-analysis/jobs/${id}`,created_at:new Date().toISOString(),retention_seconds:3600};}
function available():any{
 const start=event.raw_text.indexOf("Beirut"),source={id:17,source:"Publisher",source_platform:event.source,channel_name:event.channel_name||"",source_url:event.source_url,published_at:event.timestamp,text:event.raw_text,original_text_sha256:sourceHash()};
 return {...queued(),status:"available",result:{contract_version:"selected-report-local-analysis-v1",source,
  report:{...source,coordinates:null,severity:null,assessment_status:"model_generated_unreviewed",relevance:"relevant",stance:"denied",mentions:{place_mentions:[{text:"Beirut",start_utf16:start,end_utf16:start+6,status:"source_mention_not_event_location"}],actor_mentions:[],quantity_mentions:[]}},
  place_review:{source_sha256:sourceHash(),status:"mentions_available",mutates_events:false,event_location_established:false,external_requests:0,truncated:false,markup_incomplete:false,mentions:[{mention_id:"b".repeat(64),name:"beirut",status:"needs_review",automatically_plottable:false,span:{text:"Beirut",start_utf16:start,end_utf16:start+6}}]},
  provenance:{model:"qwen3.5:4b",model_digest:"c".repeat(64),system_sha256:"d".repeat(64)},model_excerpt_sha256:sourceHash(),model_excerpt_characters:Array.from(event.raw_text).length,source_snapshot_sha256:"e".repeat(64),coordinates:null,severity:null,critical_alert_eligible:false,mutates_events:false}};
}
let host:HTMLDivElement,root:Root,mounted:boolean;
const button=()=>host.querySelector<HTMLButtonElement>("button")!;
async function expand(){await act(async()=>{const details=host.querySelector<HTMLDetailsElement>("details")!;details.open=true;details.dispatchEvent(new Event("toggle"));});}
function answer(input:RequestInfo|URL,init?:RequestInit){return Promise.resolve(Response.json(String(input).endsWith("/briefing/status")?{local_ai:{enabled:true,model:"qwen3.5:4b"}}:init?.method==="POST"?queued():available(),{status:init?.method==="POST"?202:200}));}
beforeEach(()=>{
 (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();
 vi.stubGlobal("crypto",{subtle:{digest:async(_algorithm:string,data:Uint8Array)=>new Uint8Array(createHash("sha256").update(data).digest()).buffer}});
 request.mockReset().mockImplementation(answer);localStorage.clear();sessionStorage.clear();
 host=document.createElement("div");document.body.append(host);root=createRoot(host);mounted=true;
});
afterEach(async()=>{if(mounted)await act(async()=>root.unmount());host.remove();vi.useRealTimers();vi.unstubAllGlobals();});

describe("selected source local proposal validation",()=>{
 it("validates literal Unicode source bindings without accepting a position or severity",async()=>{
  const result=await validateReportAnalysis(available(),event,sourceHash(),id);
  expect(result.result?.report.stance).toBe("denied");expect(result.result?.place_review.event_location_established).toBe(false);
 });
 it.each(["job","sourceHash","raw","platform","citation","time","excerpt","coordinates","severity","critical","contract","digest","span","place","stance","mutates"])("rejects %s mismatch",async kind=>{
  const value=available();
  if(kind==="job")value.job_id="22222222-2222-4222-8222-222222222222";
  if(kind==="sourceHash")value.source_sha256="0".repeat(64);
  if(kind==="raw")value.result.source.text="Changed source";
  if(kind==="platform")value.result.source.source_platform="telegram";
  if(kind==="citation")value.result.source.source_url="https://other.example";
  if(kind==="time")value.result.source.published_at="not a timestamp";
  if(kind==="excerpt")value.result.report.text="Invented summary";
  if(kind==="coordinates")value.result.coordinates={lat:1,lon:1};
  if(kind==="severity")value.result.report.severity=9;
  if(kind==="critical")value.result.critical_alert_eligible=true;
  if(kind==="contract")value.result.contract_version="different";
  if(kind==="digest")value.result.provenance.model_digest=12;
  if(kind==="span")value.result.report.mentions.place_mentions[0].start_utf16--;
  if(kind==="place")value.result.place_review.mentions[0].automatically_plottable=true;
  if(kind==="stance")value.result.report.stance="confirmed";
  if(kind==="mutates")value.result.mutates_events="false";
  await expect(validateReportAnalysis(value,event,sourceHash(),id)).rejects.toThrow();
 });
 it("does not display a result attached to a failed job",async()=>{
  await expect(validateReportAnalysis({...available(),status:"failed"},event,sourceHash(),id)).rejects.toThrow();
 });
 it("rejects missing, malformed or expired retention metadata",async()=>{
  for(const patch of [{created_at:undefined},{created_at:"invalid"},{created_at:new Date(Date.now()+60000).toISOString()},{created_at:new Date(Date.now()-3600001).toISOString()},{retention_seconds:"3600"}])
   await expect(validateReportAnalysis({...available(),...patch},event,sourceHash(),id)).rejects.toThrow();
 });
 it.each([["relevant"],{value:"relevant"},null,9,true])("rejects non-string relevance or stance %j",async malformed=>{
  for(const field of ["relevance","stance"]){const value=available();value.result.report[field]=malformed;
   await expect(validateReportAnalysis(value,event,sourceHash(),id)).rejects.toThrow();}
 });
});

describe("selected source analysis lifecycle",()=>{
 it("makes no GET before expansion and no inference before explicit action",async()=>{
  await act(async()=>root.render(<ReportAnalysis event={event} operatorKey="fixture-key"/>));expect(request).not.toHaveBeenCalled();
  await expand();expect(request).toHaveBeenCalledTimes(1);expect(request.mock.calls[0][0]).toBe("/api/briefing/status");
  expect(request.mock.calls.some(([,init])=>init?.method==="POST")).toBe(false);
 });
 it("binds the explicit request to source hash and shows escaped unreviewed proposals",async()=>{
  await act(async()=>root.render(<ReportAnalysis event={event} operatorKey="fixture-key"/>));await expand();await act(async()=>button().click());
  const post=request.mock.calls.find(([,init])=>init?.method==="POST")!;
  expect(post[0]).toBe("/api/report-analysis/17");expect(JSON.parse(String(post[1]?.body))).toEqual({expected_source_sha256:sourceHash()});
  expect(post[1]?.headers).toEqual({"Content-Type":"application/json","X-Admin-Key":"fixture-key"});
  expect(host.textContent).toContain("Local proposal ready · unreviewed");expect(host.textContent).toContain("Wording: denied");
  expect(host.querySelector("img")).toBeNull();expect(host.querySelector("mark")?.textContent).toBe("Beirut");expect(host.textContent).not.toContain("fixture-key");
  expect(localStorage.length+sessionStorage.length).toBe(0);expect(host.textContent).toContain("No event fields were changed");
 });
 it("requests operator configuration without issuing a model request",async()=>{
  const configure=vi.fn();await act(async()=>root.render(<ReportAnalysis event={event} onConfigureOperator={configure}/>));await expand();await act(async()=>button().click());
  expect(configure).toHaveBeenCalledTimes(1);expect(request.mock.calls.some(([,init])=>init?.method==="POST")).toBe(false);
 });
 it.each(["SourcePermissionRequired","SourceChanged"])("exposes %s without a stale result or automatic retry",async code=>{
  request.mockImplementation((input,init)=>init?.method==="POST"?Promise.resolve(Response.json({detail:{code}},{status:code==="SourceChanged"?409:403})):answer(input,init));
  await act(async()=>root.render(<ReportAnalysis event={event} operatorKey="fixture-key"/>));await expand();await act(async()=>button().click());await act(async()=>vi.advanceTimersByTimeAsync(20000));
  expect(host.textContent).toContain(code==="SourceChanged"?"source or its provenance changed":"requires permission");expect(host.textContent).not.toContain("Topic proposal:");
  expect(request.mock.calls.filter(([,init])=>init?.method==="POST")).toHaveLength(1);
 });
 it("serializes polling and aborts late results when selection changes",async()=>{
  let release!:(r:Response)=>void;
  request.mockImplementation((input,init)=>String(input).includes("/jobs/")?new Promise(resolve=>{release=resolve;}):answer(input,init));
  await act(async()=>root.render(<ReportAnalysis event={event} operatorKey="fixture-key"/>));await expand();await act(async()=>button().click());
  await act(async()=>vi.advanceTimersByTimeAsync(30000));expect(request.mock.calls.filter(([input])=>String(input).includes("/jobs/"))).toHaveLength(1);
  const signal=request.mock.calls.find(([input])=>String(input).includes("/jobs/"))![1]!.signal as AbortSignal;
  await act(async()=>root.render(<ReportAnalysis event={{...event,id:18,raw_text:"Different report"}} operatorKey="fixture-key"/>));expect(signal.aborted).toBe(true);
  await act(async()=>release(Response.json(available())));expect(host.textContent).not.toContain("Topic proposal:");expect(host.querySelector("details")!.open).toBe(false);
 });
 it("retires pending POST when the same event's source provenance changes",async()=>{
  let release!:(r:Response)=>void;
  request.mockImplementation((input,init)=>init?.method==="POST"?new Promise(resolve=>{release=resolve;}):answer(input,init));
  await act(async()=>root.render(<ReportAnalysis event={event} operatorKey="fixture-key"/>));await expand();await act(async()=>button().click());
  const signal=request.mock.calls.find(([,init])=>init?.method==="POST")![1]!.signal as AbortSignal;
  await act(async()=>root.render(<ReportAnalysis event={{...event,reports:[{source:"telegram"}]}} operatorKey="fixture-key"/>));
  expect(signal.aborted).toBe(true);await act(async()=>release(Response.json(queued(),{status:202})));
  expect(request.mock.calls.filter(([input])=>String(input).includes("/jobs/"))).toHaveLength(0);
 });
 it("retires a displayed result immediately when source channel name changes",async()=>{
  await act(async()=>root.render(<ReportAnalysis event={event} operatorKey="fixture-key"/>));await expand();await act(async()=>button().click());
  expect(host.textContent).toContain("Topic proposal:");
  await act(async()=>root.render(<ReportAnalysis event={{...event,channel_name:"Changed publisher"}} operatorKey="fixture-key"/>));
  expect(host.textContent).not.toContain("Topic proposal:");expect(host.querySelector("details")!.open).toBe(false);
  await expect(validateReportAnalysis(available(),{...event,channel_name:"Changed publisher"},sourceHash(),id)).rejects.toThrow();
 });
 it("clears poll timer and aborts owned work on unmount",async()=>{
  request.mockImplementation((input,init)=>String(input).includes("/jobs/")?Promise.resolve(Response.json({...queued(),status:"running"})):answer(input,init));
  await act(async()=>root.render(<ReportAnalysis event={event} operatorKey="fixture-key"/>));await expand();await act(async()=>button().click());
  const before=request.mock.calls.length,signals=request.mock.calls.map(([,init])=>init?.signal).filter(Boolean) as AbortSignal[];
  await act(async()=>root.unmount());mounted=false;await act(async()=>vi.advanceTimersByTimeAsync(60000));
  expect(request).toHaveBeenCalledTimes(before);expect(signals.every(signal=>signal.aborted)).toBe(true);
 });
 it("reopening checks the same job without creating another inference request",async()=>{
  let polls=0;request.mockImplementation((input,init)=>String(input).includes("/jobs/")?Promise.resolve(Response.json(++polls===1?{...queued(),status:"running"}:available())):answer(input,init));
  await act(async()=>root.render(<ReportAnalysis event={event} operatorKey="fixture-key"/>));await expand();await act(async()=>button().click());
  await act(async()=>{const details=host.querySelector<HTMLDetailsElement>("details")!;details.open=false;details.dispatchEvent(new Event("toggle"));});
  await act(async()=>vi.advanceTimersByTimeAsync(10000));expect(polls).toBe(1);await expand();
  expect(host.textContent).toContain("Topic proposal:");expect(request.mock.calls.filter(([,init])=>init?.method==="POST")).toHaveLength(1);
 });
 it("expires a displayed result after one hour without automatic inference",async()=>{
  await act(async()=>root.render(<ReportAnalysis event={event} operatorKey="fixture-key"/>));await expand();await act(async()=>button().click());
  expect(host.textContent).toContain("Topic proposal:");const before=request.mock.calls.length;
  await act(async()=>vi.advanceTimersByTimeAsync(3600001));expect(host.textContent).not.toContain("Topic proposal:");expect(host.textContent).toContain("result expired");expect(request).toHaveBeenCalledTimes(before);
 });
 it("withholds a previous result during reopen and honors changed permission",async()=>{
  await act(async()=>root.render(<ReportAnalysis event={event} operatorKey="fixture-key"/>));await expand();await act(async()=>button().click());
  expect(host.textContent).toContain("Topic proposal:");
  await act(async()=>{const details=host.querySelector<HTMLDetailsElement>("details")!;details.open=false;details.dispatchEvent(new Event("toggle"));});
  let release!:(r:Response)=>void;request.mockImplementation((input,init)=>String(input).endsWith("/briefing/status")?new Promise(resolve=>{release=resolve;}):Promise.resolve(Response.json({...queued(),status:"source_permission_required"})));
  await expand();expect(host.textContent).not.toContain("Topic proposal:");await act(async()=>release(Response.json({local_ai:{enabled:true,model:"qwen3.5:4b"}})));
  expect(host.textContent).toContain("requires permission");expect(host.textContent).not.toContain("Topic proposal:");
 });
});
