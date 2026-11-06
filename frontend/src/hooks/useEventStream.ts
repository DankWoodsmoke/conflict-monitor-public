import { useCallback, useEffect, useRef, useState } from "react";
import { nowMs } from "../lib/clock";
import { SHOWCASE, websocketUrl, API_BASE } from "../lib/runtime";
import { apiFetch } from "../lib/api";
import { readDeliveryBaseline, readDeliveryPage, requiresDeliveryBaseline, validReport, type DeliveryCursor } from "../lib/eventDelivery";
import { MAX_LOADED_REPORTS, paginateReports, reportPageParams, type HistoryStatus } from "../lib/history";
import type { ConflictEvent } from "../types/event";

const BASELINE_LIMIT = 50;
const DELIVERY_PAGE_LIMIT = 100;
const DELIVERY_MAX_PAGES = 10;
const DELIVERY_POLL_MS = 15_000;
// Let the bounded publisher's 500 ms idle poll commit before following a WS hint.
const DELIVERY_HINT_MS = 750;
const DELIVERY_RETRY_MS = 5_000;

function mergeEvents(existing:ConflictEvent[],incoming:ConflictEvent[]):ConflictEvent[]{
  const byId=new Map(existing.map(event=>[event.id,event]));
  for(const event of incoming)byId.set(event.id,event);
  return [...byId.values()].sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp)||b.id-a.id).slice(0,MAX_LOADED_REPORTS);
}

export function useEventStream(enabled=true){
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
  const requestedHistoryRef=useRef<string|null>(null);
  const merge=useCallback((page:ConflictEvent[])=>{
    eventsRef.current=mergeEvents(eventsRef.current,page);setEvents(eventsRef.current);
  },[]);

  const fetchHistory=useCallback(async(after:string,resetCursor=false)=>{
    if(!enabled)return;
    requestedHistoryRef.current=after;
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
    if(controllerRef.current===controller)controllerRef.current=null;
    if(status!=="cancelled" && generation===generationRef.current)setHistoryStatus(status);
  },[merge,enabled]);

  useEffect(()=>{
    if(!enabled){eventsRef.current=[];setEvents([]);setIsConnected(false);setHistoryStatus("idle");setRecoveryStatus("idle");return;}
    activeRef.current=true;
    let cancelled=false;
    const initialController=new AbortController();
    const current=()=>!cancelled&&activeRef.current;
    const recentStart=()=>new Date(nowMs()-7*86400000).toISOString();
    let cursor:DeliveryCursor|null=null;
    let recoveryTimer:ReturnType<typeof setTimeout>|undefined;
    let scheduledAt=Infinity, retryNotBefore=0;
    let recovering=false, pendingHint=false, refreshHistory=false;

    const invalidateHistory=()=>{
      const interrupted=controllerRef.current!==null;
      controllerRef.current?.abort();
      controllerRef.current=null;
      generationRef.current++;
      return interrupted;
    };
    const schedule=(delay:number)=>{
      if(!current()||SHOWCASE)return;
      if(recovering){pendingHint=true;return;}
      const now=Date.now(),due=Math.max(now+delay,retryNotBefore);
      if(due>=scheduledAt)return;
      clearTimeout(recoveryTimer);
      scheduledAt=due;
      recoveryTimer=setTimeout(()=>{scheduledAt=Infinity;void reconcile();},due-now);
    };
    const fetchDelivery=(path:string)=>apiFetch(`${API_BASE}/events/delivery/${path}`,{
      signal:initialController.signal,cache:"no-store",
    });
    const reconcile=async()=>{
      if(!current()||recovering)return;
      recovering=true;
      let delay=DELIVERY_POLL_MS;
      try{
        if(!cursor){
          setRecoveryStatus("loading");
          const response=await fetchDelivery(`baseline?limit=${BASELINE_LIMIT}`);
          if(!response.ok)throw new Error("Delivery baseline unavailable");
          const baseline=readDeliveryBaseline(await response.json(),BASELINE_LIMIT);
          if(!current())return;
          invalidateHistory();
          eventsRef.current=[];
          merge(baseline.events);
          cursor={epoch:baseline.epoch,after:baseline.after};
          refreshHistory=true;
        }
        for(let pageIndex=0;current()&&pageIndex<DELIVERY_MAX_PAGES;pageIndex++){
          const limit=DELIVERY_PAGE_LIMIT;
          const query=new URLSearchParams({epoch:cursor.epoch,after:cursor.after,limit:String(limit)});
          const response=await fetchDelivery(`changes?${query}`);
          if(!current())return;
          if(response.status===409&&requiresDeliveryBaseline(await response.json())){
            if(!current())return;
            cursor=null;
            invalidateHistory();
            refreshHistory=false;
            setRecoveryStatus("loading");
            delay=DELIVERY_HINT_MS;
            return;
          }
          if(!response.ok)throw new Error("Report recovery unavailable");
          const page=readDeliveryPage(await response.json(),cursor,limit);
          if(!current())return;
          if(page.changes.length){
            const final=new Map<number,ConflictEvent|null>();
            for(const change of page.changes)final.set(change.event_id,change.event);
            // Discard pre-delete history responses before they can restore a removed report.
            if(page.changes.some(change=>change.action==="delete")&&invalidateHistory())refreshHistory=true;
            eventsRef.current=eventsRef.current.filter(event=>!final.has(event.id));
            merge([...final.values()].filter((event):event is ConflictEvent=>event!==null));
          }
          // Only the fully validated REST page acknowledges publication offsets.
          cursor={epoch:cursor.epoch,after:page.next_after};
          if(!page.has_more){setRecoveryStatus("loaded");return;}
        }
        if(current()){setRecoveryStatus("limited");delay=DELIVERY_HINT_MS;}
      }catch{
        if(current()){
          setRecoveryStatus("error");
          if(!cursor)setHistoryStatus("error");
          retryNotBefore=Date.now()+DELIVERY_RETRY_MS;
          delay=DELIVERY_RETRY_MS;
        }
      }finally{
        recovering=false;
        if(current()&&refreshHistory&&cursor){
          refreshHistory=false;
          void fetchHistory(requestedHistoryRef.current??recentStart(),true);
        }
        const nextDelay=pendingHint?Math.min(delay,DELIVERY_HINT_MS):delay;
        pendingHint=false;
        schedule(nextDelay);
      }
    };
    const connect=()=>{
      if(SHOWCASE||!current())return;
      const ws=new WebSocket(websocketUrl());wsRef.current=ws;
      let opened=false;
      ws.onopen=()=>{
        if(!current()||wsRef.current!==ws||opened)return;
        opened=true;setIsConnected(true);
        schedule(0);
      };
      ws.onmessage=message=>{
        if(!current()||wsRef.current!==ws)return;
        try{
          const data:{type?:string}|null=JSON.parse(message.data);
          if(data?.type==="new_event")schedule(DELIVERY_HINT_MS);
        }catch{/* A malformed hint cannot affect delivery state. */}
      };
      ws.onclose=()=>{
        if(!current()||wsRef.current!==ws)return;
        setIsConnected(false);wsRef.current=null;
        clearTimeout(reconnectRef.current);reconnectRef.current=setTimeout(connect,3000);
      };
      ws.onerror=()=>ws.close();
    };
    void apiFetch(`${API_BASE}/config`,{signal:initialController.signal}).then(response=>response.ok?response.json():{}).then((config:{conflict_start_date?:string})=>{
      if(current()&&!SHOWCASE&&typeof config.conflict_start_date==="string"&&Number.isFinite(Date.parse(config.conflict_start_date))){const start=new Date(config.conflict_start_date).toISOString();historyStartRef.current=start;setHistoryStart(start);}
    }).catch(()=>{});
    if(SHOWCASE)void(async()=>{
      setHistoryStatus("loading");
      try{
        const response=await apiFetch(`${API_BASE}/events?limit=50`,{signal:initialController.signal});
        if(response.ok){const page:ConflictEvent[]=await response.json();if(current()&&Array.isArray(page)&&page.every(validReport))merge(page);}
      }catch{/* Backfill reports failure explicitly. */}
      if(!current())return;
      await fetchHistory(recentStart());
    })();
    else{
      connect();
      void reconcile();
    }
    return()=>{
      cancelled=true;activeRef.current=false;generationRef.current++;
      initialController.abort();controllerRef.current?.abort();
      clearTimeout(recoveryTimer);
      clearTimeout(reconnectRef.current);
      const ws=wsRef.current;wsRef.current=null;
      if(ws){ws.onopen=null;ws.onmessage=null;ws.onclose=null;ws.onerror=null;ws.close();}
    };
  },[fetchHistory,merge,enabled]);

  const loadFullHistory=useCallback(()=>fetchHistory(historyStartRef.current),[fetchHistory]);
  return {events,isConnected,latestEvent:events[0]??null,loadFullHistory,historyStatus,recoveryStatus,historyTruncated:historyStatus==="limited"||events.length>=MAX_LOADED_REPORTS,historyStart};
}
