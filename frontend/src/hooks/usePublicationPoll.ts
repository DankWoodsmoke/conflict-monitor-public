import {useEffect,useState} from "react";
import {apiFetch} from "../lib/api";

/** Serial, deadline-bounded reads; timeout never reuses an aborted signal. */
export function usePublicationPoll<T>(url:string,interval:number,enabled:boolean,validate:(value:unknown)=>value is T){
 const [data,setData]=useState<T|null>(null),[failed,setFailed]=useState(false),[receivedAt,setReceivedAt]=useState<number|null>(null);
 useEffect(()=>{
  if(!enabled){setData(null);setFailed(false);setReceivedAt(null);return;}
  let stopped=false,next:ReturnType<typeof setTimeout>|undefined,deadline:ReturnType<typeof setTimeout>|undefined;
  let controller:AbortController|undefined;
  const poll=async()=>{
   controller=new AbortController();const signal=controller.signal;
   try{
    const value=await Promise.race([
     (async()=>{const response=await apiFetch(url,{signal});if(!response.ok)throw Error("Publication unavailable");return response.json();})(),
     new Promise<never>((_,reject)=>{deadline=setTimeout(()=>{controller?.abort();reject(Error("Publication deadline"));},15000);}),
    ]);
    if(!validate(value))throw Error("Invalid publication");
    if(!stopped){setData(value);setFailed(false);setReceivedAt(Date.now());}
   }catch{if(!stopped)setFailed(true);}finally{clearTimeout(deadline);if(!stopped)next=setTimeout(poll,interval);}
  };
  void poll();return()=>{stopped=true;clearTimeout(next);clearTimeout(deadline);controller?.abort();};
 },[url,interval,enabled,validate]);
 return {data,failed,receivedAt};
}
