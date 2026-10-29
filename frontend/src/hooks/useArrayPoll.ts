import {useEffect,useState} from "react";
import {apiFetch} from "../lib/api";

export type PollState={state:"loading"|"received"|"stale"|"unavailable";lastSuccessAt:number|null};
/** Serial, abortable refresh. HTTP receipt does not establish provider freshness. */
export function useArrayPoll<T>(url:string,interval:number,ttl:number,enabled=true){
 const [data,setData]=useState<T[]>([]);
 const [status,setStatus]=useState<PollState>({state:"loading",lastSuccessAt:null});
 useEffect(()=>{
  if(!enabled)return;
  let cancelled=false,lastSuccess=0,timer:ReturnType<typeof setTimeout>|undefined;
  let controller:AbortController|null=null;
  const poll=async()=>{
   controller=new AbortController();
   try{
    const response=await apiFetch(url,{signal:controller.signal});
    if(!response.ok)throw new Error("Provider snapshot unavailable");
    const result:unknown=await response.json();
    if(!Array.isArray(result))throw new Error("Invalid snapshot shape");
    if(cancelled)return;
    lastSuccess=Date.now();setData(result);setStatus({state:"received",lastSuccessAt:lastSuccess});
   }catch{
    if(cancelled)return;
    if(!lastSuccess||Date.now()-lastSuccess>=ttl)setData([]);
    setStatus({state:lastSuccess?"stale":"unavailable",lastSuccessAt:lastSuccess||null});
   }finally{if(!cancelled)timer=setTimeout(poll,interval);}
  };
  void poll();return()=>{cancelled=true;controller?.abort();clearTimeout(timer);};
 },[url,interval,ttl,enabled]);
 return {data,status};
}
