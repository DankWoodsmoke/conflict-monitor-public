import { useCallback, useEffect, useRef, useState } from "react";
import { nowMs } from "../lib/clock";
import { SHOWCASE, websocketUrl, API_BASE } from "../lib/runtime";
import { apiFetch } from "../lib/api";
import { MAX_LOADED_REPORTS, paginateReports, reportPageParams, type HistoryStatus } from "../lib/history";
import type { ConflictEvent, EventWSMessage } from "../types/event";

function validReport(event:ConflictEvent):boolean {
  return Number.isSafeInteger(event?.id) && event.id>0 && Number.isFinite(Date.parse(event?.timestamp));
}

function mergeEvents(existing:ConflictEvent[],incoming:ConflictEvent[]):ConflictEvent[]{
  const byId=new Map(existing.map(event=>[event.id,event]));
  for(const event of incoming)byId.set(event.id,event);
  return [...byId.values()].sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp)||b.id-a.id).slice(0,MAX_LOADED_REPORTS);
}

export function useEventStream(){
  const [events,setEvents]=useState<ConflictEvent[]>([]);
  const eventsRef=useRef<ConflictEvent[]>([]);
  const [isConnected,setIsConnected]=useState(false);
  const [historyStatus,setHistoryStatus]=useState<HistoryStatus>("idle");
  const [recoveryStatus,setRecoveryStatus]=useState<HistoryStatus>("idle");
  const [historyStart,setHistoryStart]=useState(()=>new Date(SHOWCASE?nowMs()-86400000:(import.meta.env.VITE_HISTORY_START || "2026-02-28T00:00:00Z")).toISOString());
  const historyStartRef=useRef(historyStart);
  const activeRef=useRef(false);
  const generationRef=useRef(0);
  const wsRef=useRef<WebSocket|null>(null);
  const reconnectRef=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const controllerRef=useRef<AbortController|null>(null);
  const recoveryControllerRef=useRef<AbortController|null>(null);
  const maxSeenIdRef=useRef(0);
  // Retain an unfinished REST cursor separately: newer WS messages must not jump over a gap.
  const recoveryCursorRef=useRef<number|null>(null);
  const merge=useCallback((page:ConflictEvent[])=>{
    for(const event of page)maxSeenIdRef.current=Math.max(maxSeenIdRef.current,event.id);
    eventsRef.current=mergeEvents(eventsRef.current,page);setEvents(eventsRef.current);
  },[]);

  const fetchHistory=useCallback(async(after:string,resetCursor=false)=>{
    const generation=++generationRef.current;
    controllerRef.current?.abort();const controller=new AbortController();controllerRef.current=controller;
    const oldest=resetCursor?undefined:eventsRef.current[eventsRef.current.length-1];
    setHistoryStatus("loading");
    const status=await paginateReports({after,before:oldest?.timestamp,beforeId:oldest?.id,
      remaining:()=>MAX_LOADED_REPORTS-eventsRef.current.length,
      cancelled:()=>!activeRef.current||generation!==generationRef.current,
      fetchPage:async(query)=>{const response=await apiFetch(`${API_BASE}/events?${reportPageParams(query)}`,{signal:controller.signal});if(!response.ok)throw new Error("History unavailable");return response.json();},
      onPage:merge,
    });
    if(status!=="cancelled" && generation===generationRef.current)setHistoryStatus(status);
  },[merge]);

  useEffect(()=>{
    activeRef.current=true;
    let cancelled=false;
    const initialController=new AbortController();
    const current=()=>!cancelled&&activeRef.current;
    const reconcile=async(ws:WebSocket,startId:number)=>{
      recoveryControllerRef.current?.abort();
      const controller=new AbortController();recoveryControllerRef.current=controller;
      const currentSocket=()=>current()&&wsRef.current===ws&&!controller.signal.aborted;
      setRecoveryStatus("loading");
      let cursor=startId,fetched=0;
      try{
        // Source publication time may predate the outage. Only a creation-ID cursor recovers it.
        while(currentSocket()&&fetched<MAX_LOADED_REPORTS){
          const limit=Math.min(500,MAX_LOADED_REPORTS-fetched);
          const query=new URLSearchParams({after_id:String(cursor),limit:String(limit)});
          const response=await apiFetch(`${API_BASE}/events?${query}`,{signal:controller.signal});
          if(!currentSocket())return;
          if(!response.ok)throw new Error("Report recovery unavailable");
          const page:ConflictEvent[]=await response.json();
          if(!currentSocket())return;
          if(!Array.isArray(page)||page.length>limit)throw new Error("Invalid report recovery page");
          let previous=cursor;
          for(const event of page){
            if(!validReport(event)||event.id<=previous)throw new Error("Invalid report recovery order");
            previous=event.id;
          }
          merge(page);fetched+=page.length;cursor=previous;
          recoveryCursorRef.current=cursor;
          if(page.length<limit){recoveryCursorRef.current=null;setRecoveryStatus("loaded");return;}
        }
        if(currentSocket())setRecoveryStatus("limited");
      }catch{
        if(currentSocket())setRecoveryStatus("error");
      }finally{
        if(recoveryControllerRef.current===controller)recoveryControllerRef.current=null;
      }
    };
    const connect=()=>{
      if(SHOWCASE||!current())return;
      const ws=new WebSocket(websocketUrl());wsRef.current=ws;
      let opened=false;
      ws.onopen=()=>{
        if(!current()||wsRef.current!==ws||opened)return;
        opened=true;setIsConnected(true);
        // Capture before any asynchronous work or concurrent WS delivery advances maxSeenId.
        const cursor=recoveryCursorRef.current??maxSeenIdRef.current;
        recoveryCursorRef.current=cursor;
        void reconcile(ws,cursor);
      };
      ws.onmessage=message=>{if(!current()||wsRef.current!==ws)return;try{const data:EventWSMessage=JSON.parse(message.data);if(data.type==="new_event"&&validReport(data.event))merge([data.event]);}catch{/* Invalid transport data is not displayed. */}};
      ws.onclose=()=>{
        if(!current()||wsRef.current!==ws)return;
        setIsConnected(false);wsRef.current=null;
        if(recoveryControllerRef.current){recoveryControllerRef.current.abort();setRecoveryStatus("error");}
        clearTimeout(reconnectRef.current);reconnectRef.current=setTimeout(connect,3000);
      };
      ws.onerror=()=>ws.close();
    };
    void apiFetch(`${API_BASE}/config`,{signal:initialController.signal}).then(response=>response.ok?response.json():{}).then((config:{conflict_start_date?:string})=>{
      if(current()&&!SHOWCASE&&typeof config.conflict_start_date==="string"&&Number.isFinite(Date.parse(config.conflict_start_date))){const start=new Date(config.conflict_start_date).toISOString();historyStartRef.current=start;setHistoryStart(start);}
    }).catch(()=>{});
    void(async()=>{
      setHistoryStatus("loading");
      try{
        const response=await apiFetch(`${API_BASE}/events?limit=50`,{signal:initialController.signal});
        if(response.ok){const page:ConflictEvent[]=await response.json();if(current()&&Array.isArray(page)&&page.every(validReport))merge(page);}
      }catch{/* Backfill reports failure explicitly. */}
      if(!current())return;
      // Establish a REST baseline first; recovery covers the interval before this socket opens.
      connect();
      await fetchHistory(new Date(nowMs()-7*86400000).toISOString());
    })();
    return()=>{
      cancelled=true;activeRef.current=false;generationRef.current++;
      initialController.abort();controllerRef.current?.abort();recoveryControllerRef.current?.abort();
      clearTimeout(reconnectRef.current);
      const ws=wsRef.current;wsRef.current=null;
      if(ws){ws.onopen=null;ws.onmessage=null;ws.onclose=null;ws.onerror=null;ws.close();}
    };
  },[fetchHistory,merge]);

  const loadFullHistory=useCallback(()=>fetchHistory(historyStartRef.current),[fetchHistory]);
  return {events,isConnected,latestEvent:events[0]??null,loadFullHistory,historyStatus,recoveryStatus,historyTruncated:historyStatus==="limited"||events.length>=MAX_LOADED_REPORTS,historyStart};
}
