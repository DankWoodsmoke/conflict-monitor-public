export interface CaptionSegment {text:string;sourceId:number|null;duration:number;sha256:string}
export interface CaptionPlan {identity:string;filename:string;videoSha256:string;videoDuration:number;segments:CaptionSegment[]}
export type CaptionResult={status:"ready";plan:CaptionPlan;vtt:string}|{status:"unavailable";reason:"metadata"|"crypto"|"digest"};
const record=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==="object"&&!Array.isArray(v);
const sha=(v:unknown):v is string=>typeof v==="string"&&/^[a-f0-9]{64}$/.test(v);
function safeText(text:string){
  if(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(text))return false;
  for(let i=0;i<text.length;i++){const c=text.charCodeAt(i);if(c>=0xd800&&c<=0xdbff){const next=text.charCodeAt(++i);if(!(next>=0xdc00&&next<=0xdfff))return false;}else if(c>=0xdc00&&c<=0xdfff)return false;}
  return true;
}

/** Read only the bounded timing/text fields used by captions, never a URL. */
export function parseCaptionPlan(value:unknown):CaptionPlan|null{
  if(!record(value)||value.status!=="available"||typeof value.filename!=="string"||!/^[a-f0-9]{32}\.mp4$/.test(value.filename)||!sha(value.sha256)||!value.sha256.startsWith(value.filename.slice(0,32)))return null;
  const duration=value.duration_seconds,sources=value.sources,segments=value.segments,validation=value.validation;
  if(typeof duration!=="number"||!Number.isFinite(duration)||duration<=0||duration>245||!Array.isArray(sources)||sources.length<1||sources.length>4||!Array.isArray(segments)||segments.length!==sources.length+2||segments.length<3||segments.length>6||!record(validation)||validation.full_decode!=="passed"||validation.streams!=="h264_and_aac"||!Array.isArray(validation.audio_segments)||validation.audio_segments.length!==segments.length)return null;
  const ids=sources.map(s=>record(s)?s.id:null);
  if(!ids.every(id=>Number.isSafeInteger(id)&&(id as number)>0)||new Set(ids).size!==ids.length)return null;
  let total=0,characters=0,previousMs=0;
  const result:CaptionSegment[]=[];
  for(let i=0;i<segments.length;i++){
    const segment=segments[i],audio=validation.audio_segments[i];
    if(!record(segment)||typeof segment.narration!=="string"||!segment.narration.trim()||segment.narration.length>2400||!safeText(segment.narration)||!record(audio)||audio.segment!==i||typeof audio.duration_seconds!=="number"||!Number.isFinite(audio.duration_seconds)||audio.duration_seconds<=0||audio.duration_seconds>90||!sha(audio.narration_sha256))return null;
    const sourceId=i>0&&i<segments.length-1?ids[i-1] as number:null;
    if(sourceId===null?segment.source_id!=null:segment.source_id!==sourceId)return null;
    total+=audio.duration_seconds;characters+=segment.narration.length;
    const endMs=Math.round(total*1000);if(endMs<=previousMs||characters>12000||total>240)return null;previousMs=endMs;
    result.push({text:segment.narration,sourceId,duration:audio.duration_seconds,sha256:audio.narration_sha256});
  }
  // Preserve measured audio boundaries; do not stretch them to video length.
  // The small container/codec rounding difference is bounded, not word timing.
  if(Math.abs(total-duration)>0.25)return null;
  const identity=JSON.stringify([value.filename,value.sha256,duration,result]);
  return {identity,filename:value.filename,videoSha256:value.sha256,videoDuration:duration,segments:result};
}

export function vttTime(ms:number){
  const hours=Math.floor(ms/3600000),minutes=Math.floor(ms/60000)%60,seconds=Math.floor(ms/1000)%60;
  return `${String(hours).padStart(2,"0")}:${String(minutes).padStart(2,"0")}:${String(seconds).padStart(2,"0")}.${String(ms%1000).padStart(3,"0")}`;
}
export function captionVtt(plan:CaptionPlan){
  let elapsed=0,previous=0;
  const cues=plan.segments.map((segment,index)=>{
    elapsed+=segment.duration;const end=Math.round(elapsed*1000);
    // No raw markup, blank-line block injection or cue timing delimiter can
    // escape into the VTT payload. The separate transcript retains exact text.
    const text=segment.text.replace(/[\r\n\t]+/g," ").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    const cue=`segment-${index+1}\n${vttTime(previous)} --> ${vttTime(end)}\n${text}`;previous=end;return cue;
  });
  return `WEBVTT\n\n${cues.join("\n\n")}\n`;
}
export async function prepareBriefingCaptions(plan:CaptionPlan,digest:Pick<SubtleCrypto,"digest">|null=globalThis.crypto?.subtle??null):Promise<CaptionResult>{
  if(!digest)return {status:"unavailable",reason:"crypto"};
  try{
    for(const segment of plan.segments){
      const bytes=await digest.digest("SHA-256",new TextEncoder().encode(segment.text));
      const actual=Array.from(new Uint8Array(bytes),v=>v.toString(16).padStart(2,"0")).join("");
      if(actual!==segment.sha256)return {status:"unavailable",reason:"digest"};
    }
    return {status:"ready",plan,vtt:captionVtt(plan)};
  }catch{return {status:"unavailable",reason:"digest"};}
}
