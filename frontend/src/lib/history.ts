import type { ConflictEvent } from "../types/event";

export const MAX_LOADED_REPORTS=5000;
export type HistoryStatus="idle"|"loading"|"loaded"|"limited"|"error";
export interface ReportPageQuery {limit:number;after:string;before?:string;before_id?:number}
export function reportPageParams(query:ReportPageQuery):string {
  const params=new URLSearchParams({limit:String(query.limit),after:query.after});
  if(query.before){params.set("before",query.before);if(query.before_id!=null)params.set("before_id",String(query.before_id));}
  return params.toString();
}

/** Bound history work and retain the ID tie-breaker when timestamps are equal. */
export async function paginateReports(options:{
  after:string;before?:string;beforeId?:number;
  remaining:()=>number;cancelled:()=>boolean;
  fetchPage:(query:ReportPageQuery)=>Promise<ConflictEvent[]>;
  onPage:(page:ConflictEvent[])=>void;
}):Promise<Exclude<HistoryStatus,"idle"|"loading">|"cancelled"> {
  let before=options.before,beforeId=options.beforeId;
  let fetched=0;
  try {
    while(!options.cancelled()){
      const remaining=Math.min(options.remaining(),MAX_LOADED_REPORTS-fetched);if(remaining<=0)return "limited";
      const limit=Math.min(500,remaining);
      const page=await options.fetchPage({limit,after:options.after,before,before_id:beforeId});
      if(options.cancelled())return "cancelled";
      if(!Array.isArray(page)||page.length>limit)return "error";
      let previousTime=before==null?Infinity:Date.parse(before),previousId=beforeId??Infinity;
      const ids=new Set<number>();
      for(const report of page){
        const time=Date.parse(report?.timestamp);
        if(!Number.isSafeInteger(report?.id)||!Number.isFinite(time)||time<Date.parse(options.after)||ids.has(report.id))return "error";
        if(time>previousTime||(time===previousTime&&report.id>=previousId))return "error";
        previousTime=time;previousId=report.id;ids.add(report.id);
      }
      fetched+=page.length;
      options.onPage(page);
      if(page.length<limit)return "loaded";
      const last=page[Math.min(page.length,limit)-1];
      if(!last || !Number.isFinite(last.id) || !Number.isFinite(Date.parse(last.timestamp)))return "error";
      if(last.timestamp===before && last.id===beforeId)return "error";
      before=last.timestamp;beforeId=last.id;
    }
    return "cancelled";
  }catch{return options.cancelled()?"cancelled":"error";}
}
