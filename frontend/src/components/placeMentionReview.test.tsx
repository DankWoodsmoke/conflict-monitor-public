import {createHash,webcrypto} from "node:crypto";
import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {beforeEach,afterEach,describe,it,expect,vi} from "vitest";
import {PlaceMentionReview,validatePlaceReview} from "./PlaceMentionReview";
import type {ConflictEvent} from "../types/event";

const request=vi.hoisted(()=>vi.fn());
vi.mock("../lib/api",()=>({apiFetch:request}));
const event={id:91,raw_text:"🛰️ No explosion in Beirut; <img src=x> is source text."} as ConflictEvent;
function fixture(source=event){
 const start=source.raw_text.indexOf("Beirut");
 return {event_id:source.id,source_sha256:createHash("sha256").update(source.raw_text).digest("hex"),status:"mentions_available",mutates_events:false,event_location_established:false,external_requests:0,truncated:false,markup_incomplete:false,mentions:[{mention_id:"a".repeat(64),name:"beirut",status:"needs_review",automatically_plottable:false,span:{text:"Beirut",start_utf16:start,end_utf16:start+6}}]};
}
let host:HTMLDivElement,root:Root;
beforeEach(()=>{vi.stubGlobal("crypto",webcrypto);(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;request.mockReset();host=document.createElement("div");document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.unstubAllGlobals();});
async function settled(){
 // Keep the native WebCrypto completion inside React's async update boundary.
 for(let attempt=0;attempt<100;attempt++){
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,10));});
  if(host.querySelector<HTMLButtonElement>("button")?.disabled===false)return;
 }
 expect(host.querySelector<HTMLButtonElement>("button")?.disabled).toBe(false);
}

describe("source-bound place review",()=>{
 it("preserves literal Unicode spans and does not promote a mention",async()=>{
  const result=await validatePlaceReview(fixture(),event);expect(result.mentions[0].span.start_utf16).toBe(event.raw_text.indexOf("Beirut"));expect(result.event_location_established).toBe(false);
 });
 it.each(["hash","event","span","promoted","network","duplicate","size","status","markup"])("rejects %s mismatches",async(kind)=>{
  const value:any=fixture();
  if(kind==="hash")value.source_sha256="0".repeat(64);
  if(kind==="event")value.event_id++;
  if(kind==="span")value.mentions[0].span.start_utf16--;
  if(kind==="promoted")value.mentions[0].automatically_plottable=true;
  if(kind==="network")value.external_requests=1;
  if(kind==="duplicate")value.mentions.push({...value.mentions[0]});
  if(kind==="size")value.mentions=Array(25).fill(value.mentions[0]);
  if(kind==="status")value.status="verified";
  if(kind==="markup")value.markup_incomplete="false";
  await expect(validatePlaceReview(value,event)).rejects.toThrow();
 });
 it("shows incomplete markup coverage alongside preserved literal mentions",async()=>{
  request.mockResolvedValue(Response.json({...fixture(),markup_incomplete:true}));
  await act(async()=>root.render(<PlaceMentionReview event={event}/>));
  await act(async()=>host.querySelector<HTMLButtonElement>("button")!.click());await settled();
  expect(host.textContent).toContain("Place coverage is incomplete");expect(host.querySelector("mark")?.textContent).toBe("Beirut");
 });
 it("makes no request until activated, displays escaped source context and has no plot action",async()=>{
  request.mockResolvedValue(Response.json(fixture()));await act(async()=>root.render(<PlaceMentionReview event={event}/>));expect(request).not.toHaveBeenCalled();
  await act(async()=>host.querySelector<HTMLButtonElement>("button")!.click());
  await settled();
  expect(request).toHaveBeenCalledTimes(1);expect(request.mock.calls[0][0]).toBe("/api/events/91/location-candidates");expect(request.mock.calls[0][1].method).toBeUndefined();
  expect(host.textContent).toContain("No incident position established");expect(host.textContent).toContain("No explosion");expect(host.querySelector("mark")?.textContent).toBe("Beirut");expect(host.querySelector("img")).toBeNull();expect(host.querySelectorAll("button")).toHaveLength(1);
 });
 it("retains an explicit error and retries after a missing backend route",async()=>{
  request.mockResolvedValueOnce(Response.json({detail:"not available"},{status:404})).mockResolvedValueOnce(Response.json(fixture()));
  await act(async()=>root.render(<PlaceMentionReview event={event}/>));await act(async()=>host.querySelector<HTMLButtonElement>("button")!.click());expect(host.querySelector('[role="alert"]')).not.toBeNull();
  await act(async()=>host.querySelector<HTMLButtonElement>("button")!.click());await settled();expect(host.querySelector('[role="alert"]')).toBeNull();expect(host.querySelector("mark")?.textContent).toBe("Beirut");
 });
 it("aborts stale work when a new event replaces the selected source",async()=>{
  let finish!:(r:Response)=>void;request.mockReturnValue(new Promise<Response>(resolve=>{finish=resolve;}));
  await act(async()=>root.render(<PlaceMentionReview event={event}/>));await act(async()=>host.querySelector<HTMLButtonElement>("button")!.click());const signal=request.mock.calls[0][1].signal as AbortSignal;
  await act(async()=>root.render(<PlaceMentionReview event={{...event,id:92,raw_text:"New source in Tehran"}}/>));expect(signal.aborted).toBe(true);
  await act(async()=>finish(Response.json(fixture())));expect(host.querySelector("mark")).toBeNull();expect(host.querySelector('[role="alert"]')).toBeNull();expect(host.querySelector<HTMLButtonElement>("button")?.disabled).toBe(false);
 });
});
