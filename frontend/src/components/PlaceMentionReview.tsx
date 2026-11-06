import {useEffect,useRef,useState} from "react";
import type {ConflictEvent} from "../types/event";
import {apiFetch} from "../lib/api";
import "../styles/place-review.css";

type Mention={mention_id:string;name:string;status:string;span:{text:string;start_utf16:number;end_utf16:number};automatically_plottable:false};
type Review={event_id:number;source_sha256:string;status:string;mentions:Mention[];truncated:boolean;markup_incomplete:boolean;mutates_events:false;event_location_established:false;external_requests:0};

async function sourceHash(text:string){
  const hash=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(text));
  return [...new Uint8Array(hash)].map(value=>value.toString(16).padStart(2,"0")).join("");
}
export async function validatePlaceReview(value:unknown,event:Pick<ConflictEvent,"id"|"raw_text">):Promise<Review>{
  if(!value||typeof value!=="object")throw new Error("Invalid review");
  const review=value as Review;
  if(review.event_id!==event.id||review.source_sha256!==await sourceHash(event.raw_text)||review.mutates_events!==false||review.event_location_established!==false||review.external_requests!==0||!Array.isArray(review.mentions)||review.mentions.length>24||typeof review.truncated!=="boolean"||typeof review.markup_incomplete!=="boolean"||!["mentions_available","no_known_mentions","source_too_large"].includes(review.status))throw new Error("Review does not match this source");
  const ids=new Set<string>();
  for(const mention of review.mentions){
    const span=mention?.span;
    if(typeof mention?.mention_id!=="string"||!/^[a-f0-9]{64}$/.test(mention.mention_id)||ids.has(mention.mention_id)||typeof mention.name!=="string"||mention.name.length>240||!["needs_review","disambiguation_required"].includes(mention.status)||mention.automatically_plottable!==false||!span||typeof span.text!=="string"||!span.text||!Number.isInteger(span.start_utf16)||!Number.isInteger(span.end_utf16)||span.start_utf16<0||span.end_utf16<=span.start_utf16||span.end_utf16>event.raw_text.length||event.raw_text.slice(span.start_utf16,span.end_utf16)!==span.text)throw new Error("Invalid source span");
    ids.add(mention.mention_id);
  }
  if((review.status==="mentions_available")!==(review.mentions.length>0))throw new Error("Inconsistent review");
  return review;
}

export function PlaceMentionReview({event}:{event:ConflictEvent}){
  const [review,setReview]=useState<Review|null>(null),[error,setError]=useState(""),[loading,setLoading]=useState(false);
  const current=useRef<AbortController|null>(null);
  useEffect(()=>{current.current?.abort();current.current=null;setReview(null);setError("");setLoading(false);return()=>current.current?.abort();},[event.id,event.raw_text]);
  async function load(){
    current.current?.abort();const controller=new AbortController();current.current=controller;setLoading(true);setError("");setReview(null);
    try{
      const response=await apiFetch(`/api/events/${event.id}/location-candidates`,{signal:controller.signal});
      if(!response.ok)throw new Error("Review unavailable");
      const checked=await validatePlaceReview(await response.json(),event);
      if(!controller.signal.aborted&&current.current===controller)setReview(checked);
    }catch{
      if(!controller.signal.aborted&&current.current===controller)setError("Place review is unavailable or does not match the current source. No position was changed.");
    }finally{if(!controller.signal.aborted&&current.current===controller)setLoading(false);}
  }
  return <section className="place-mention-review" aria-label="Place mention review">
    <button type="button" onClick={()=>void load()} disabled={loading}>{loading?"Reviewing source…":review?"Refresh place mentions":"Review place mentions"}</button>
    <p>This checks names in source prose, excluding markup and URLs. A mention can be an origin, destination, denial or quotation; it does not locate an incident.</p>
    {error&&<p role="alert">{error}</p>}
    {review&&<div role="status">
      {review.markup_incomplete&&<p>Some source markup was ambiguous and excluded. Place coverage is incomplete; inspect the preserved source.</p>}
      {review.status==="source_too_large"?<p>This source exceeds the bounded review size. Its text is unchanged.</p>:review.mentions.length===0?<p>No names matched the local reference inventory. This review supplies no additional location evidence; language and coverage gaps are possible.</p>:<>
        <p><strong>No incident position established.</strong> These candidates are not added to Earth.</p>
        <ul>{review.mentions.map(mention=><li key={mention.mention_id}>
          <strong>{mention.span.text}</strong> · {mention.status==="disambiguation_required"?"Locality/facility ambiguity; further evidence required":"Unreviewed place mention"}
          <blockquote>{event.raw_text.slice(Math.max(0,mention.span.start_utf16-75),mention.span.start_utf16)}<mark>{mention.span.text}</mark>{event.raw_text.slice(mention.span.end_utf16,mention.span.end_utf16+75)}</blockquote>
        </li>)}</ul>
      </>}
      {review.truncated&&<p>Only the first 24 mentions are shown; this review is incomplete.</p>}
    </div>}
  </section>;
}
