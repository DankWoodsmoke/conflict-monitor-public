import {act,useEffect} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {useEventStream} from "./useEventStream";
import {apiFetch} from "../lib/api";
import {buildShowcase} from "../lib/showcase";
import type {ConflictEvent} from "../types/event";

vi.mock("../lib/api",()=>({apiFetch:vi.fn()}));
vi.mock("../lib/runtime",()=>({SHOWCASE:false,API_BASE:"/api",websocketUrl:()=>"ws://localhost/events"}));
const fetchMock=vi.mocked(apiFetch);
const fixture=buildShowcase(Date.parse("2026-10-29T03:00:00Z")).events[0];
const report=(id:number,timestamp="2026-10-29T02:00:00Z"):ConflictEvent=>({...fixture,id,timestamp,summary:`Report ${id}`});
class Socket {
  static instances:Socket[]=[];
  onopen:((event:Event)=>void)|null=null;
  onmessage:((event:MessageEvent)=>void)|null=null;
  onclose:((event:Event)=>void)|null=null;
  onerror:((event:Event)=>void)|null=null;
  constructor(_url:string){Socket.instances.push(this);}
  open(){this.onopen?.(new Event("open"));}
  message(event:ConflictEvent){this.onmessage?.(new MessageEvent("message",{data:JSON.stringify({type:"new_event",event})}));}
  close(){this.onclose?.(new Event("close"));}
}
let host:HTMLDivElement,root:Root,latest:ReturnType<typeof useEventStream>,mounted:boolean;
function Harness(){const value=useEventStream();useEffect(()=>{latest=value;},[value]);return <output>{value.events.map(e=>e.id).join(",")}</output>;}
const query=(input:RequestInfo|URL)=>new URL(String(input),"http://localhost").searchParams;
function defaultResponse(input:RequestInfo|URL):Promise<Response>{
  return Promise.resolve(Response.json(String(input).endsWith("/config")?{}:query(input).get("limit")==="50"?[report(10)]:[]));
}
const last=<T,>(items:T[]):T=>items[items.length-1];
async function mount(){await act(async()=>root.render(<Harness/>));expect(Socket.instances).toHaveLength(1);}
async function open(socket=last(Socket.instances)){await act(async()=>socket.open());}
async function reconnect(){await act(async()=>last(Socket.instances).close());await act(async()=>vi.advanceTimersByTimeAsync(3000));return last(Socket.instances);}
beforeEach(()=>{
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-29T03:00:00Z"));
  vi.stubGlobal("WebSocket",Socket);Socket.instances=[];fetchMock.mockReset().mockImplementation(defaultResponse);
  host=document.createElement("div");document.body.append(host);root=createRoot(host);mounted=true;
});
afterEach(async()=>{if(mounted)await act(async()=>root.unmount());host.remove();vi.unstubAllGlobals();vi.useRealTimers();});

describe("WebSocket report recovery",()=>{
 it("recovers a newly created ID with older publication time once despite concurrent WS messages",async()=>{
  await mount();await open();const socket=await reconnect();let release!:(response:Response)=>void;
  fetchMock.mockImplementation((input)=>query(input).has("after_id")?new Promise(resolve=>{release=resolve;}):defaultResponse(input));
  await open(socket);const recoveryCalls=()=>fetchMock.mock.calls.filter(([input])=>query(input).has("after_id"));
  expect(query(last(recoveryCalls())[0]).get("after_id")).toBe("10");
  await act(async()=>{socket.message(report(13));socket.message(report(11,"2026-10-01T00:00:00Z"));socket.open();});
  expect(recoveryCalls()).toHaveLength(2);
  await act(async()=>release(Response.json([report(11,"2026-10-01T00:00:00Z"),report(12,"2026-10-02T00:00:00Z")])));
  expect(latest.events.map(e=>e.id)).toEqual([13,10,12,11]);expect(latest.recoveryStatus).toBe("loaded");
  expect(latest.events.filter(e=>e.id===11)).toHaveLength(1);expect(host.textContent).toContain("12");
 });
 it("paginates by REST page cursor instead of a higher concurrent WS ID",async()=>{
  await mount();await open();const socket=await reconnect();let release!:(response:Response)=>void;
  const input=Array.from({length:1101},(_,i)=>report(i+11,"2026-10-01T00:00:00Z"));const cursors:number[]=[];
  fetchMock.mockImplementation((url)=>{
    const q=query(url);if(!q.has("after_id"))return defaultResponse(url);
    const cursor=Number(q.get("after_id"));cursors.push(cursor);
    if(cursors.length===1)return new Promise(resolve=>{release=resolve;});
    return Promise.resolve(Response.json(input.filter(e=>e.id>cursor).slice(0,Number(q.get("limit")))));
  });
  await open(socket);await act(async()=>socket.message(report(9000)));await act(async()=>release(Response.json(input.slice(0,500))));
  expect(cursors).toEqual([10,510,1010]);expect(latest.events).toHaveLength(1103);expect(latest.recoveryStatus).toBe("loaded");
 });
 it("limits each connection to 5000 fetched reports and retains unfinished cursor across reconnect",async()=>{
  await mount();await open();let socket=await reconnect();const cursors:number[]=[];
  fetchMock.mockImplementation((url)=>{
    const q=query(url);if(!q.has("after_id"))return defaultResponse(url);
    const cursor=Number(q.get("after_id"));cursors.push(cursor);
    return Promise.resolve(Response.json(Array.from({length:Math.min(5210-cursor,Number(q.get("limit")))},(_,i)=>report(cursor+i+1,"2026-10-01T00:00:00Z"))));
  });
  await open(socket);expect(cursors).toHaveLength(10);expect(last(cursors)).toBe(4510);
  expect(latest.recoveryStatus).toBe("limited");expect(latest.events).toHaveLength(5000);
  await act(async()=>socket.message(report(9999)));socket=await reconnect();await open(socket);
  expect(cursors[10]).toBe(5010);expect(cursors).toHaveLength(11);expect(latest.recoveryStatus).toBe("loaded");
 });
 it("aborts interrupted request and ignores late response while next connection resumes the gap",async()=>{
  await mount();await open();const oldSocket=await reconnect();let release!:(response:Response)=>void;let signal:AbortSignal|null|undefined;
  fetchMock.mockImplementation((url,init)=>query(url).has("after_id")?new Promise(resolve=>{release=resolve;signal=init?.signal;}):defaultResponse(url));
  await open(oldSocket);await act(async()=>oldSocket.message(report(99)));const socket=await reconnect();expect(signal?.aborted).toBe(true);
  fetchMock.mockImplementation((url)=>Promise.resolve(Response.json(query(url).has("after_id")?[report(11,"2026-10-01T00:00:00Z")]:[])));await open(socket);
  const requests=fetchMock.mock.calls.filter(([url])=>query(url).has("after_id"));expect(query(last(requests)[0]).get("after_id")).toBe("10");
  await act(async()=>release(Response.json([report(12)])));
  expect(latest.events.map(e=>e.id)).toEqual([99,10,11]);expect(latest.recoveryStatus).toBe("loaded");
 });
 it.each([[report(12),report(11)],[report(11),report(11)],[report(10)],[report(11,"invalid")]])("rejects malformed or nonadvancing pages without publishing them",async(...page)=>{
  await mount();await open();const socket=await reconnect();fetchMock.mockResolvedValue(Response.json(page));await open(socket);
  expect(latest.events.map(e=>e.id)).toEqual([10]);expect(latest.recoveryStatus).toBe("error");
 });
 it("aborts recovery and reconnect timers on unmount without publishing a late result",async()=>{
  await mount();await open();const socket=await reconnect();let release!:(response:Response)=>void;let signal:AbortSignal|null|undefined;
  fetchMock.mockImplementation((_url,init)=>new Promise(resolve=>{release=resolve;signal=init?.signal;}));await open(socket);
  await act(async()=>root.unmount());mounted=false;expect(signal?.aborted).toBe(true);
  await act(async()=>{release(Response.json([report(11)]));await vi.advanceTimersByTimeAsync(9000);});
  expect(Socket.instances).toHaveLength(2);expect(host.textContent).toBe("");
 });
});
