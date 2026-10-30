import {describe,expect,it,vi} from "vitest";
import {captionVtt,parseCaptionPlan,prepareBriefingCaptions} from "./briefingCaptions";

const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>("node:crypto");
async function fixture(texts=["Opening narration.","Source seven reports a statement.","These are attributed reports, not verified incidents."]){
 const hashes=await Promise.all(texts.map(async text=>Array.from(new Uint8Array(await webcrypto.subtle.digest("SHA-256",new TextEncoder().encode(text))),n=>n.toString(16).padStart(2,"0")).join("")));
 return {status:"available",filename:"a".repeat(32)+".mp4",sha256:"a".repeat(64),duration_seconds:7,sources:[{id:7}],
  segments:texts.map((narration,i)=>({narration,...(i===1?{source_id:7}:{})})),
  validation:{full_decode:"passed",streams:"h264_and_aac",audio_segments:[1.125,2.333,3.517].map((duration_seconds,segment)=>({segment,duration_seconds,narration_sha256:hashes[segment]}))}};
}

describe("measured source narration captions",()=>{
 it("verifies exact narration UTF-8 and uses cumulative measured boundaries without stretching to container length",async()=>{
  const plan=parseCaptionPlan(await fixture())!;const result=await prepareBriefingCaptions(plan,webcrypto.subtle);
  expect(result.status).toBe("ready");if(result.status!=="ready")throw Error("Expected captions");
  expect(result.vtt).toContain("00:00:00.000 --> 00:00:01.125");expect(result.vtt).toContain("00:00:01.125 --> 00:00:03.458");expect(result.vtt).toContain("00:00:03.458 --> 00:00:06.975");
  expect(plan.segments.map(s=>s.sourceId)).toEqual([null,7,null]);expect(result.vtt).not.toContain("00:00:07.000");
 });
 it("keeps exact non-ASCII transcript text while escaping markup, arrows and blank-line cue injection",async()=>{
  const text="المصدر 😀 & <script>\n\n00:00:00.000 --> 99:00:00.000\t<b>quoted</b>";
  const plan=parseCaptionPlan(await fixture([text,"Middle.","End."]))!;
  const result=await prepareBriefingCaptions(plan,webcrypto.subtle);expect(result.status).toBe("ready");
  const vtt=captionVtt(plan);expect(vtt).toContain("المصدر 😀 &amp; &lt;script&gt; 00:00:00.000 --&gt; 99:00:00.000 &lt;b&gt;quoted&lt;/b&gt;");
  expect(vtt.match(/ --> /g)).toHaveLength(3);expect(plan.segments[0].text).toBe(text);
 });
 it("fails closed for changed narration, unavailable crypto and digest errors",async()=>{
  const plan=parseCaptionPlan(await fixture())!;plan.segments[1].text+=" changed";
  expect(await prepareBriefingCaptions(plan,webcrypto.subtle)).toEqual({status:"unavailable",reason:"digest"});
  expect(await prepareBriefingCaptions(plan,null)).toEqual({status:"unavailable",reason:"crypto"});
  expect(await prepareBriefingCaptions(plan,{digest:vi.fn().mockRejectedValue(Error("unsupported"))})).toEqual({status:"unavailable",reason:"digest"});
 });
 it("binds artifact identity to consumed metadata, not polling clocks",async()=>{
  const value=await fixture(),baseline=parseCaptionPlan(value)!;
  expect(parseCaptionPlan({...value,generated_at:"changed",runtime_state:{state:"running"}})?.identity).toBe(baseline.identity);
  const changed=structuredClone(value);changed.validation.audio_segments[0].duration_seconds+=0.01;
  expect(parseCaptionPlan(changed)?.identity).not.toBe(baseline.identity);
 });
 it("rejects artifact/hash, source membership and audio index/order mismatches",async()=>{
  const original=await fixture();
  const mutations:Array<(v:any)=>void>=[v=>v.sha256="b".repeat(64),v=>v.filename="../video.mp4",v=>v.sources[0].id=0,v=>v.segments[1].source_id=8,v=>v.segments[0].source_id=7,v=>v.validation.audio_segments[1].segment=0,v=>v.validation.audio_segments.reverse(),v=>v.validation.audio_segments[0].narration_sha256="invalid",v=>v.validation.full_decode="failed"];
  for(const mutate of mutations){const v=structuredClone(original);mutate(v);expect(parseCaptionPlan(v)).toBeNull();}
 });
 it("bounds count, duration, total alignment and invalid timing numbers",async()=>{
  const original=await fixture();
  const mutations:Array<(v:any)=>void>=[v=>v.segments.pop(),v=>v.segments.push(v.segments[0]),v=>v.validation.audio_segments.pop(),v=>v.sources.push({id:7}),v=>v.duration_seconds=8,v=>v.duration_seconds=Infinity,...[0,-1,NaN,Infinity,91,0.0001].map(n=>(v:any)=>v.validation.audio_segments[0].duration_seconds=n)];
  for(const mutate of mutations){const v=structuredClone(original);mutate(v);expect(parseCaptionPlan(v)).toBeNull();}
 });
 it("rejects unbounded narration, control characters and malformed Unicode before crypto",async()=>{
  const original=await fixture();
  for(const text of [" ","x".repeat(2401),"bad\u0000text","bad\u001btext","bad\ud800text","bad\udc00text"]){const v=structuredClone(original);v.segments[0].narration=text;expect(parseCaptionPlan(v)).toBeNull();}
 });
});
