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
const endpoint=(input:RequestInfo|URL)=>new URL(String(input),"http://localhost");
const baseline=(events=[report(10)],epoch="fixture-live",after="100")=>Response.json({epoch,after,events});
const upsert=(offset:string,event:ConflictEvent)=>({offset,event_id:event.id,action:"upsert",event});
const tombstone=(offset:string,event_id:number)=>({offset,event_id,action:"delete",event:null});
const changes=(after:string,rows:ReturnType<typeof upsert | typeof tombstone>[]=[],hasMore=false,epoch="fixture-live")=>
  Response.json({epoch,changes:rows,next_after:rows.at(-1)?.offset??after,has_more:hasMore});
const isChanges=(url:RequestInfo|URL)=>endpoint(url).pathname.endsWith("/delivery/changes");
const seenCursors=()=>fetchMock.mock.calls.filter(([input])=>isChanges(input)).map(([input])=>endpoint(input).searchParams.get("after"));

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
function Harness(){
  const value=useEventStream();
  useEffect(()=>{latest=value;},[value]);
  return <output>{value.events.map(e=>e.id).join(",")}</output>;
}
function defaultResponse(input:RequestInfo|URL):Promise<Response>{
  const url=endpoint(input);
  if(url.pathname.endsWith("/delivery/baseline"))return Promise.resolve(baseline());
  if(isChanges(input))return Promise.resolve(changes(url.searchParams.get("after")!));
  return Promise.resolve(Response.json(url.pathname.endsWith("/config")?{}:[]));
}
const last=<T,>(items:T[]):T=>items[items.length-1];
const wait=async(ms:number)=>act(async()=>vi.advanceTimersByTimeAsync(ms));
async function mount(){await act(async()=>root.render(<Harness/>));expect(Socket.instances).toHaveLength(1);}
async function open(socket=last(Socket.instances)){await act(async()=>socket.open());await wait(0);}
async function close(){await act(async()=>last(Socket.instances).close());}
async function hint(id:number){await act(async()=>last(Socket.instances).message(report(id)));await wait(750);}
const ids=()=>latest.events.map(event=>event.id);

beforeEach(()=>{
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
  vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-29T03:00:00Z"));
  vi.stubGlobal("WebSocket",Socket);Socket.instances=[];
  fetchMock.mockReset().mockImplementation(defaultResponse);
  host=document.createElement("div");document.body.append(host);root=createRoot(host);mounted=true;
});
afterEach(async()=>{if(mounted)await act(async()=>root.unmount());host.remove();vi.unstubAllGlobals();vi.useRealTimers();});

describe("committed report recovery",()=>{
  it("recovers a late lower Event ID after a higher ID committed, with WS and history unable to advance acknowledgement",async()=>{
    await mount();
    let stage=0;
    fetchMock.mockImplementation(async(input)=>{
      const url=endpoint(input);
      if(isChanges(input)){
        if(stage++===0)return changes("100",[upsert("101",report(12))]);
        return changes("101",[upsert("102",report(11,"2026-10-01T00:00:00Z"))]);
      }
      if(url.pathname.endsWith("/events"))return Response.json([report(9000,"2026-10-28T00:00:00Z")]);
      return defaultResponse(input);
    });
    await act(async()=>latest.loadFullHistory());
    await hint(9999);
    expect(ids()).toEqual([12,10,9000]);
    await close();await wait(3000);await open();
    expect(seenCursors()).toEqual(["100","100","101"]);
    expect(ids()).toEqual([12,10,9000,11]);
    expect(latest.recoveryStatus).toBe("loaded");
  });

  it("preserves an in-flight REST page across socket loss and serializes a second hint",async()=>{
    await mount();
    let release!:(response:Response)=>void;
    let signal:AbortSignal|null|undefined;
    fetchMock.mockImplementation((input,init)=>{
      if(!isChanges(input))return defaultResponse(input);
      if(endpoint(input).searchParams.get("after")==="101")return Promise.resolve(changes("101",[upsert("103",report(13))]));
      return new Promise(resolve=>{release=resolve;signal=init?.signal;});
    });
    await open();await close();await wait(3000);await open();
    await hint(500);
    expect(signal?.aborted).toBe(false);
    expect(seenCursors()).toEqual(["100","100"]);
    await act(async()=>release(changes("100",[upsert("101",report(11))])));
    await wait(750);
    expect(seenCursors()).toEqual(["100","100","101"]);
    expect(ids()).toEqual([13,11,10]);
  });

  it("polls after missing WS hints and preserves canonical bigint cursors with mode gaps",async()=>{
    fetchMock.mockImplementation(async(input)=>{
      if(endpoint(input).pathname.endsWith("/delivery/baseline"))return baseline([report(10)],"fixture-live","9223372036854775801");
      if(isChanges(input))return changes("9223372036854775801");
      return defaultResponse(input);
    });
    await mount();
    fetchMock.mockImplementation((input)=>isChanges(input)?Promise.resolve(changes("9223372036854775801",[
      upsert("9223372036854775805",report(12)),upsert("9223372036854775807",report(11))
    ])):defaultResponse(input));
    await wait(15000);
    expect(seenCursors()).toEqual(["9223372036854775801","9223372036854775801"]);
    expect(ids()).toEqual([12,11,10]);
  });

  it("bounds pages and resumes from the last accepted offset without waiting for a reconnect",async()=>{
    let total=0;
    fetchMock.mockImplementation((input)=>{
      if(!isChanges(input))return defaultResponse(input);
      const query=endpoint(input).searchParams,after=Number(query.get("after")),limit=Number(query.get("limit"));
      expect(limit).toBe(100);
      const count=Math.min(1001-total,limit);
      total+=count;
      return Promise.resolve(changes(String(after),Array.from({length:count},(_,index)=>upsert(String(after+index+1),report(after+index+1))),total<1001));
    });
    await mount();
    expect(seenCursors()).toHaveLength(10);
    expect(last(seenCursors())).toBe("1000");
    expect(latest.recoveryStatus).toBe("limited");
    await wait(750);
    expect(seenCursors()[10]).toBe("1100");
    expect(latest.recoveryStatus).toBe("loaded");
    expect(ids()).toHaveLength(1002);
  });

  it.each([
    ["unordered",[upsert("102",report(12)),upsert("101",report(11))],"101","fixture-live",false],
    ["repeated offset",[upsert("101",report(11)),upsert("101",report(12))],"101","fixture-live",false],
    ["mismatched ID",[{...upsert("101",report(11)),event_id:12}],"101","fixture-live",false],
    ["leading zero",[upsert("0101",report(11))],"0101","fixture-live",false],
    ["overflow",[upsert("9223372036854775808",report(11))],"9223372036854775808","fixture-live",false],
    ["ahead ack",[upsert("101",report(11))],"102","fixture-live",false],
    ["wrong epoch",[upsert("101",report(11))],"101","other-live",false],
    ["empty with more",[],"100","fixture-live",true],
  ])("rejects a %s page atomically and retries from the prior offset",async(_name,rows,next_after,epoch,has_more)=>{
    await mount();
    fetchMock.mockImplementation((input)=>isChanges(input)?Promise.resolve(Response.json({epoch,changes:rows,next_after,has_more})):defaultResponse(input));
    await hint(99);
    expect(ids()).toEqual([10]);
    expect(latest.recoveryStatus).toBe("error");
    fetchMock.mockImplementation((input)=>isChanges(input)?Promise.resolve(changes("100",[upsert("101",report(11))])):defaultResponse(input));
    await wait(5000);
    expect(seenCursors()).toEqual(["100","100","100"]);
    expect(ids()).toEqual([11,10]);
  });

  it("reseeds only for an explicit expired cursor and replaces stale reports",async()=>{
    await mount();
    fetchMock.mockImplementation(async(input)=>{
      const url=endpoint(input);
      if(url.pathname.endsWith("/delivery/baseline"))return baseline([report(13)],"new-live","500");
      if(isChanges(input)){
        if(url.searchParams.get("epoch")==="new-live")return changes("500",[],false,"new-live");
        return Response.json({detail:{code:"delivery_baseline_required",reason:"cursor_expired"}},{status:409});
      }
      return defaultResponse(input);
    });
    await hint(99);await wait(750);
    expect(seenCursors()).toEqual(["100","100","500"]);
    expect(ids()).toEqual([13]);
  });

  it("invalidates a pre-delete history page and ignores an older WS payload",async()=>{
    await mount();
    let release!:(response:Response)=>void;
    let historySignal:AbortSignal|null|undefined;
    fetchMock.mockImplementation((input,init)=>{
      const url=endpoint(input);
      if(isChanges(input))return Promise.resolve(changes("100",[tombstone("101",10)]));
      if(url.pathname.endsWith("/events")&&!release)return new Promise(resolve=>{release=resolve;historySignal=init?.signal;});
      return defaultResponse(input);
    });
    await act(async()=>{void latest.loadFullHistory();});
    await hint(10);
    expect(historySignal?.aborted).toBe(true);
    await act(async()=>release(Response.json([report(10)])));
    expect(ids()).toEqual([]);
  });

  it("cancels fetch and scheduled work when unmounted",async()=>{
    await mount();
    let release!:(response:Response)=>void;
    let signal:AbortSignal|null|undefined;
    fetchMock.mockImplementation((input,init)=>isChanges(input)?new Promise(resolve=>{release=resolve;signal=init?.signal;}):defaultResponse(input));
    await open();await close();
    await act(async()=>root.unmount());mounted=false;
    expect(signal?.aborted).toBe(true);
    await act(async()=>release(changes("100",[upsert("101",report(11))])));
    await wait(18000);
    expect(Socket.instances).toHaveLength(1);
    expect(host.textContent).toBe("");
  });
});
