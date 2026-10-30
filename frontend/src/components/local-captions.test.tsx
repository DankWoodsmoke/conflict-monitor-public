import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {LocalBriefingPanel} from "./LocalBriefingPanel";
import {apiFetch} from "../lib/api";
import {captionVtt,prepareBriefingCaptions,type CaptionPlan,type CaptionResult} from "../lib/briefingCaptions";

vi.mock("../lib/api",()=>({apiFetch:vi.fn()}));
vi.mock("../lib/runtime",()=>({SHOWCASE:false,API_BASE:"/api"}));
vi.mock("../lib/briefingCaptions",async original=>({...await original<typeof import("../lib/briefingCaptions")>(),prepareBriefingCaptions:vi.fn()}));
const fetchMock=vi.mocked(apiFetch),prepare=vi.mocked(prepareBriefingCaptions);
const status={local_ai:{enabled:true,state:"ready"},video:{enabled:true,state:"ready"}};
const narration=["Opening <img src=x onerror=alert(1)>\nمرحبا 😀 & details.","Exact source seven narration.","Report limitations."];
function manifest(char="a"){return {status:"available",filename:char.repeat(32)+".mp4",sha256:char.repeat(64),duration_seconds:7,sources:[{id:7,source:"Fixture publisher",source_url:"https://example.org/7",published_at:"2026-10-30T00:00:00Z"}],segments:narration.map((text,i)=>({narration:text,...(i===1?{source_id:7}:{})})),validation:{full_decode:"passed",streams:"h264_and_aac",audio_segments:[1.125,2.333,3.517].map((duration_seconds,segment)=>({segment,duration_seconds,narration_sha256:"c".repeat(64)}))}};}
const ready=(plan:CaptionPlan):CaptionResult=>({status:"ready",plan,vtt:captionVtt(plan)});
let host:HTMLDivElement,root:Root,mounted:boolean,current:ReturnType<typeof manifest>;
let createUrl:ReturnType<typeof vi.fn<(value:Blob|MediaSource)=>string>>,revokeUrl:ReturnType<typeof vi.fn<(value:string)=>void>>;
const trackModes=new WeakMap<HTMLTrackElement,{mode:string}>(),trackLists=new WeakMap<HTMLMediaElement,EventTarget>();
let oldTrack:PropertyDescriptor|undefined,oldList:PropertyDescriptor|undefined;
function list(video:HTMLMediaElement){let value=trackLists.get(video);if(!value){value=new EventTarget();trackLists.set(video,value);}return value;}
const click=(name:string)=>[...host.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent===name)!.click();
beforeEach(()=>{
 (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();current=manifest();
 fetchMock.mockReset().mockImplementation(input=>Promise.resolve(Response.json(String(input).endsWith("/status")?status:current)));
 prepare.mockReset().mockImplementation(async plan=>ready(plan));
 let serial=0;createUrl=vi.fn((_value:Blob|MediaSource)=>`blob:fixture-${++serial}`);revokeUrl=vi.fn((_value:string)=>{});
 const NativeURL=URL;vi.stubGlobal("URL",class extends NativeURL{static createObjectURL(value:Blob|MediaSource):string{return createUrl(value) as string;}static revokeObjectURL(value:string):void{revokeUrl(value);}});
 oldTrack=Object.getOwnPropertyDescriptor(HTMLTrackElement.prototype,"track");oldList=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,"textTracks");
 Object.defineProperty(HTMLTrackElement.prototype,"track",{configurable:true,get(){let value=trackModes.get(this);if(!value){value={mode:"disabled"};trackModes.set(this,value);}return value;}});
 Object.defineProperty(HTMLMediaElement.prototype,"textTracks",{configurable:true,get(){return list(this);}});
 host=document.createElement("div");document.body.append(host);root=createRoot(host);mounted=true;
});
afterEach(async()=>{
 if(mounted)await act(async()=>root.unmount());host.remove();
 if(oldTrack)Object.defineProperty(HTMLTrackElement.prototype,"track",oldTrack);else delete (HTMLTrackElement.prototype as any).track;
 if(oldList)Object.defineProperty(HTMLMediaElement.prototype,"textTracks",oldList);else delete (HTMLMediaElement.prototype as any).textTracks;
 vi.unstubAllGlobals();vi.useRealTimers();
});

describe("caption resource and playback lifecycle",()=>{
 it("renders exact safe transcript, native captions and named controls without generation requests",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel mode="video"/>));
  const track=host.querySelector("track")!;expect(track.kind).toBe("captions");expect(track.srclang).toBe("en");expect(track.default).toBe(true);expect(track.track.mode).toBe("showing");
  expect(host.querySelector("video[controls]")).not.toBeNull();expect(host.querySelector("video[autoplay]")).toBeNull();
  expect(host.querySelector('[aria-label="Complete narration transcript"] p')?.textContent).toBe(narration[0]);expect(host.querySelector("img")).toBeNull();expect(host.textContent).toContain("not word aligned");
  expect(fetchMock.mock.calls.every(([,init])=>!init?.method)).toBe(true);
 });
 it("preserves video, playback position, user CC choice and Blob identity across repeated 15-second polls",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel mode="video"/>));const video=host.querySelector("video")!,track=host.querySelector("track")!;video.currentTime=4;
  await act(async()=>click("Hide captions"));
  await act(async()=>vi.advanceTimersByTimeAsync(45000));
  expect(host.querySelector("video")).toBe(video);expect(video.currentTime).toBe(4);expect(host.querySelector("track")).toBe(track);expect(track.track.mode).toBe("disabled");
  expect(prepare).toHaveBeenCalledOnce();expect(createUrl).toHaveBeenCalledOnce();expect(revokeUrl).not.toHaveBeenCalled();expect(host.textContent).toContain("Show captions");
 });
 it("synchronises the explicit toggle with changes made through native caption controls",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel mode="video"/>));const video=host.querySelector("video")!,track=host.querySelector("track")!;
  await act(async()=>{track.track.mode="disabled";list(video).dispatchEvent(new Event("change"));});
  expect(host.querySelector('button[aria-pressed="false"]')?.textContent).toBe("Show captions");
  await act(async()=>click("Show captions"));expect(track.track.mode).toBe("showing");
  await act(async()=>{track.track.mode="disabled";list(video).dispatchEvent(new Event("change"));});expect(host.textContent).toContain("Show captions");
 });
 it("discloses paused caption repaint limits after enable without forcing playback or moving the clock",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel mode="video"/>));const video=host.querySelector("video")!,track=host.querySelector("track")!;video.currentTime=4;
  const play=vi.spyOn(video,"play").mockResolvedValue(),pause=vi.spyOn(video,"pause").mockImplementation(()=>{});
  const hint="If captions do not appear while paused, resume playback to show them.";
  expect(host.textContent).not.toContain(hint);
  await act(async()=>click("Hide captions"));await act(async()=>click("Show captions"));expect(host.textContent).toContain(hint);
  expect(video.currentTime).toBe(4);expect(play).not.toHaveBeenCalled();expect(pause).not.toHaveBeenCalled();
  await act(async()=>video.dispatchEvent(new Event("playing")));expect(host.textContent).not.toContain(hint);
  await act(async()=>{track.track.mode="disabled";list(video).dispatchEvent(new Event("change"));});
  await act(async()=>{track.track.mode="showing";list(video).dispatchEvent(new Event("change"));});expect(host.textContent).toContain(hint);
  await act(async()=>click("Hide captions"));expect(host.textContent).not.toContain(hint);expect(host.querySelector("video")).toBe(video);expect(createUrl).toHaveBeenCalledOnce();
 });
 it("removes and revokes old captions before a new artifact finishes verification",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel mode="video"/>));const oldVideo=host.querySelector("video"),oldUrl=host.querySelector("track")!.src;let resolve!:(r:CaptionResult)=>void;
  prepare.mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));current=manifest("b");
  await act(async()=>vi.advanceTimersByTimeAsync(15000));
  expect(host.querySelector("video")).not.toBe(oldVideo);expect(host.querySelector("track")).toBeNull();expect(host.querySelector('[aria-label="Complete narration transcript"]')).toBeNull();expect(revokeUrl).toHaveBeenCalledExactlyOnceWith(oldUrl);
  await act(async()=>resolve(ready(prepare.mock.calls[1][0])));expect(host.querySelector("track")!.src).not.toBe(oldUrl);expect(createUrl).toHaveBeenCalledTimes(2);
 });
 it("replaces changed caption metadata without remounting or seeking the same video",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel mode="video"/>));const video=host.querySelector("video")!,oldUrl=host.querySelector("track")!.src;video.currentTime=4;
  current.validation.audio_segments[0].duration_seconds+=0.01;
  await act(async()=>vi.advanceTimersByTimeAsync(15000));expect(host.querySelector("video")).toBe(video);expect(video.currentTime).toBe(4);expect(revokeUrl).toHaveBeenCalledExactlyOnceWith(oldUrl);expect(createUrl).toHaveBeenCalledTimes(2);
 });
 it("never reattaches a retired Blob when earlier metadata returns while verification is pending",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel mode="video"/>));const retired=host.querySelector("track")!.src;const original=manifest();
  current.segments[1].source_id=8;await act(async()=>vi.advanceTimersByTimeAsync(15000));expect(host.querySelector("track")).toBeNull();
  let resolve!:(r:CaptionResult)=>void;prepare.mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));current=original;
  await act(async()=>vi.advanceTimersByTimeAsync(15000));expect(host.querySelector("track")).toBeNull();expect(revokeUrl).toHaveBeenCalledExactlyOnceWith(retired);
  await act(async()=>resolve(ready(prepare.mock.calls[1][0])));expect(host.querySelector("track")!.src).not.toBe(retired);
 });
 it("discards late verification on a replaced artifact and unmount, and revokes only owned URLs",async()=>{
  const pending:Array<{plan:CaptionPlan;resolve:(r:CaptionResult)=>void}>=[];prepare.mockImplementation(plan=>new Promise(resolve=>pending.push({plan,resolve})));
  await act(async()=>root.render(<LocalBriefingPanel mode="video"/>));current=manifest("b");await act(async()=>vi.advanceTimersByTimeAsync(15000));
  await act(async()=>pending[0].resolve(ready(pending[0].plan)));expect(createUrl).not.toHaveBeenCalled();
  await act(async()=>pending[1].resolve(ready(pending[1].plan)));expect(createUrl).toHaveBeenCalledOnce();const url=host.querySelector("track")!.src;
  await act(async()=>root.unmount());mounted=false;expect(revokeUrl).toHaveBeenCalledExactlyOnceWith(url);
 });
 it("keeps old videos usable when caption metadata is missing, mismatched or cannot be checked",async()=>{
  prepare.mockResolvedValue({status:"unavailable",reason:"crypto"});await act(async()=>root.render(<LocalBriefingPanel mode="video"/>));
  expect(host.querySelector("video[controls]")).not.toBeNull();expect(host.querySelector("track")).toBeNull();expect(host.textContent).toContain("browser cannot verify caption metadata");
  current.segments[1].source_id=8;await act(async()=>vi.advanceTimersByTimeAsync(15000));expect(host.querySelector("video[controls]")).not.toBeNull();expect(host.querySelector("track")).toBeNull();expect(host.querySelector('[aria-label="Complete narration transcript"]')).toBeNull();
 });
 it("retains verified transcript if the browser cannot load the caption resource",async()=>{
  await act(async()=>root.render(<LocalBriefingPanel mode="video"/>));await act(async()=>host.querySelector("track")!.dispatchEvent(new Event("error")));
  expect(host.textContent).toContain("caption track could not be loaded");expect(host.textContent).not.toContain("completed video could not be played");expect(host.querySelector('[aria-label="Complete narration transcript"]')).not.toBeNull();expect(host.querySelector('button[aria-pressed]')?.hasAttribute("disabled")).toBe(true);
 });
});
