import { describe, expect, it, vi } from "vitest";
import { MAX_LOADED_REPORTS, paginateReports, reportPageParams, type ReportPageQuery } from "./history";
import { buildShowcase } from "./showcase";

const timestamp="2026-10-28T12:00:00Z";
const base=buildShowcase(Date.parse(timestamp)).events[0];
function records(count:number){return Array.from({length:count},(_,i)=>({...base,id:count-i,timestamp}));}

describe("bounded compound report pagination",()=>{
  it("retains all reports when more than one page shares the same timestamp",async()=>{
    const input=records(1200),loaded:typeof input=[];
    const query=vi.fn(async(q:ReportPageQuery)=>input.filter(r=>q.before_id==null||r.id<q.before_id).slice(0,q.limit));
    const status=await paginateReports({after:"2026-10-01T00:00:00Z",remaining:()=>MAX_LOADED_REPORTS-loaded.length,cancelled:()=>false,fetchPage:query,onPage:page=>loaded.push(...page)});
    expect(status).toBe("loaded");expect(loaded.map(r=>r.id)).toEqual(input.map(r=>r.id));
    expect(query.mock.calls[1][0]).toMatchObject({before:timestamp,before_id:701});
    expect(query.mock.calls[2][0]).toMatchObject({before:timestamp,before_id:201});
  });
  it("stops request work and discloses the display limit rather than claiming complete history",async()=>{
    const input=records(5200),loaded:typeof input=[];
    const query=vi.fn(async(q:ReportPageQuery)=>input.filter(r=>q.before_id==null||r.id<q.before_id).slice(0,q.limit));
    const status=await paginateReports({after:"2026-10-01T00:00:00Z",remaining:()=>MAX_LOADED_REPORTS-loaded.length,cancelled:()=>false,fetchPage:query,onPage:page=>loaded.push(...page)});
    expect(status).toBe("limited");expect(loaded).toHaveLength(MAX_LOADED_REPORTS);expect(query).toHaveBeenCalledTimes(10);
  });
  it("bounds fetches even when duplicate delivery fails to advance the loaded-count callback",async()=>{
    const input=records(5200);
    const query=vi.fn(async(q:ReportPageQuery)=>input.filter(r=>q.before_id==null||r.id<q.before_id).slice(0,q.limit));
    const status=await paginateReports({after:"2026-10-01T00:00:00Z",remaining:()=>MAX_LOADED_REPORTS,cancelled:()=>false,fetchPage:query,onPage:()=>{}});
    expect(status).toBe("limited");expect(query).toHaveBeenCalledTimes(10);
  });
  it("uses only the remaining budget on the final request",async()=>{
    let remaining=1;const query=vi.fn(async(_query:ReportPageQuery)=>records(1));
    const status=await paginateReports({after:"2026-10-01T00:00:00Z",remaining:()=>remaining,cancelled:()=>false,fetchPage:query,onPage:p=>{remaining-=p.length;}});
    expect(query.mock.calls[0][0].limit).toBe(1);expect(status).toBe("limited");
  });
  it.each([
    [{...base,id:2,timestamp},{...base,id:2,timestamp}],
    [{...base,id:1,timestamp},{...base,id:2,timestamp}],
    [{...base,id:1,timestamp:"invalid"}],
  ])("rejects malformed or unordered pages before publishing them",async(...page)=>{
    const onPage=vi.fn();const status=await paginateReports({after:"2026-10-01T00:00:00Z",remaining:()=>500,cancelled:()=>false,fetchPage:async()=>page as typeof base[],onPage});
    expect(status).toBe("error");expect(onPage).not.toHaveBeenCalled();
  });
  it("serializes timestamp and ID together without losing the timezone",()=>{
    const params=new URLSearchParams(reportPageParams({limit:500,after:timestamp,before:timestamp,before_id:42}));
    expect(params.get("before")).toBe(timestamp);expect(params.get("before_id")).toBe("42");
  });
  it("does not publish a response that arrived after cancellation",async()=>{
    let cancelled=false;const onPage=vi.fn();
    const status=await paginateReports({after:timestamp,remaining:()=>500,cancelled:()=>cancelled,fetchPage:async()=>{cancelled=true;return records(1);},onPage});
    expect(status).toBe("cancelled");expect(onPage).not.toHaveBeenCalled();
  });
});
