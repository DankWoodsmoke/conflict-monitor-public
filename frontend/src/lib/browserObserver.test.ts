import {describe,expect,it,vi} from 'vitest';

// Minimal Node test-only surfaces avoid adding Node globals/types to the DOM
// application's TypeScript environment or adding a runtime dependency.
const {existsSync,readFileSync}=await vi.importActual<{existsSync:(path:string)=>boolean;readFileSync:(path:string,encoding:'utf8')=>string}>('node:fs');
const {resolve}=await vi.importActual<{resolve:(...parts:string[])=>string}>('node:path');
const {cwd}=await vi.importActual<{cwd:()=>string}>('node:process');
type Assert=((value:unknown,message?:string)=>void)&{equal:(actual:unknown,expected:unknown,message?:string)=>void};
const {strict:assert}=await vi.importActual<{strict:Assert}>('node:assert');

// Exercise the actual verifier branch without a browser, network or clock change.
// A supplied earlier root timestamp is a fixture, never a production timer override.
const toolPath='tools/observe_browser_lifecycle.cjs';
const source=readFileSync(existsSync(resolve(cwd(),toolPath))?resolve(cwd(),toolPath):resolve(cwd(),'..',toolPath),'utf8');
const start=source.indexOf('    const mode=summary.samples%3;');
const end=source.indexOf('   }catch(error)',start);
if(start<0||end<start)throw new Error('Observer branch changed; review this regression fixture');
const branch=source.slice(start,end);
const captionStart=source.indexOf('function captionMetrics(video){');
const captionEnd=source.indexOf('\n(async()=>{',captionStart);
if(captionStart<0||captionEnd<captionStart)throw Error('Observer caption validator changed; review this regression fixture');
const captionCheck=new Function(source.slice(captionStart,captionEnd)+'\nreturn captionMetrics;')() as (video:unknown)=>any;
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
async function sample(code:string){
 const summary={samples:0,generation_posts:0,page_errors:[] as string[],natural_rotation:undefined as any};
 const row={at:'fixture',elapsed_seconds:9002,findings:[]};
 const scenes:any[]=[{provider:'ready',canvas_count:1},{phase:'current',generation:2,attempt:2,root_at:Date.now(),retries:0,visibility:'visible',attribution_visible:true}];
 const page={getByRole:()=>({getByRole:()=>({click:async()=>{}})}),evaluate:async()=>true,waitForFunction:async()=>{},locator:()=>({evaluate:async()=>scenes.shift()})};
 const cdp={send:async(name:string)=>name==='Performance.getMetrics'?{metrics:[{name:'JSHeapUsedSize',value:123},{name:'JSHeapTotalSize',value:456}]}:{documents:1,nodes:10,jsEventListeners:2}};
 const run=new AsyncFunction('page','summary','row','handle','assert','cdp','longSession','firstRootMono','elapsed','baselineGeneration',code+'\nreturn {summary,row,baselineGeneration};');
 return run(page,summary,row,{},assert,cdp,true,performance.now()-9_001_000,()=>9002,1);
}
describe('actual long-session observer natural-rotation branch',()=>{
 it('reproduces the previous TDZ failure only reached when generation increases',async()=>{
  expect(branch).toContain('const performanceMetrics=await cdp.send');
  const old=branch.replace('const performanceMetrics=','const performance=').replace('performanceMetrics.metrics','performance.metrics');
  await expect(sample(old)).rejects.toThrow(/before initialization/);
 });
 it('records real natural-rotation and CDP heap fields without shadowing the monotonic clock',async()=>{
  expect(source).not.toMatch(/\b(?:const|let|var)\s+performance\s*=/);
  const result=await sample(branch);expect(result.summary.natural_rotation.generation).toBe(2);expect(result.row.heap).toEqual({JSHeapUsedSize:123,JSHeapTotalSize:456});expect(result.row.session.phase).toBe('current');
 });
 it('qualifies actual loaded caption boundaries without recording narration or resource URLs',()=>{
  const cues=[{startTime:0,endTime:11.633,text:'Private fixture narration'},{startTime:11.633,endTime:24.474,text:'Private source text'},{startTime:24.474,endTime:38.359,text:'Private limitations'}];
  const video={querySelector:()=>({readyState:2,src:'blob:private-fixture'}),textTracks:[{kind:'captions',mode:'showing',cues}]};
  const result=captionCheck(video);expect(result).toEqual({track_count:1,ready_state:2,mode:'showing',cue_count:3,timings:[{start_seconds:0,end_seconds:11.633},{start_seconds:11.633,end_seconds:24.474},{start_seconds:24.474,end_seconds:38.359}]});
  expect(JSON.stringify(result)).not.toContain('Private');expect(JSON.stringify(result)).not.toContain('blob:');
 });
 it('rejects missing, hidden, empty, malformed or overlapping captions rather than treating a video element as proof',()=>{
  const fixture=()=>({element:{readyState:2},track:{kind:'captions',mode:'showing',cues:[{startTime:0,endTime:1,text:'Opening'},{startTime:1,endTime:2,text:'Source'},{startTime:2,endTime:3,text:'Limits'}]}});
  const mutations:Array<(f:ReturnType<typeof fixture>)=>void>=[f=>f.element.readyState=1,f=>f.track.mode='disabled',f=>f.track.cues.pop(),f=>f.track.cues[1].text=' ',f=>f.track.cues[1].startTime=0.5,f=>f.track.cues[1].endTime=NaN,f=>f.track.cues[2].endTime=Infinity];
  for(const change of mutations){const f=fixture();change(f);expect(()=>captionCheck({querySelector:()=>f.element,textTracks:[f.track]})).toThrow(/caption/);}
  expect(()=>captionCheck({querySelector:()=>null,textTracks:[]})).toThrow(/caption/);
  const f=fixture();expect(()=>captionCheck({querySelector:()=>f.element,textTracks:[f.track,f.track]})).toThrow(/caption/);
  expect(branch).toContain('if(longSession){\n       await page.waitForFunction');expect(branch).toContain('row.captions=');
 });
});
