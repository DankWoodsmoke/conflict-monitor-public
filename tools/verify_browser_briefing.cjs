/* Native browser playback of the actual local artifact. Viewing never queues work. */
const {chromium,firefox,webkit}=require('../frontend/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
// Reuse the PNG decoder bundled with the pinned Playwright version. Compare
// rendered RGBA pixels, not PNG ancillary metadata or compression bytes.
const {PNG}=require('../frontend/node_modules/playwright-core/lib/utilsBundle.js');
const base=process.env.CM_BASE_URL||'http://127.0.0.1:5190';
const output=process.env.CM_BRIEFING_OUTPUT||'artifacts/browser-local-briefing';
const expectedId=Number(process.env.CM_EXPECT_SOURCE_ID||55);
const sanitize=value=>String(value).replace(/https?:\/\/[^\s"<>]+/g,'[provider URL omitted]').slice(0,700);
const result={started_at:new Date().toISOString(),base_url:base,scope:'actual_source_bound_local_artifact_mobile_browser_playback',cases:[],limitations:[
 '390x844 viewport/touch emulation is not a physical mobile device.',
 'Advancing playback/decoding does not certify listener audibility or pronunciation.',
 'Source truth and model labels remain unreviewed; this probe never starts generation.',
 'No external live stream status is inferred from local recorded artifact playback.']};
fs.mkdirSync(output,{recursive:true});
function save(){fs.writeFileSync(path.join(output,'receipt.json'),JSON.stringify(result,null,2));}
const digest=value=>createHash('sha256').update(value).digest('hex');
async function verifyCaptions(page,video,manifest,row){
 const segments=manifest.segments,audio=manifest.validation?.audio_segments;
 assert(Array.isArray(segments)&&Array.isArray(audio)&&segments.length===audio.length&&segments.length>=3,'Measured caption metadata unavailable');
 const narration=segments.map(segment=>segment.narration);
 assert(narration.every(text=>typeof text==='string'&&text.length>0),'Narration transcript metadata unavailable');
 await page.waitForFunction(()=>{const t=document.querySelector('video[aria-label="Narrated attributed source briefing"] track[kind="captions"]');return t&&t.readyState===2&&t.track.cues?.length>0;},null,{timeout:20000});
 const track=await video.evaluate(v=>{const t=v.querySelector('track[kind="captions"]');return{label:t.label,language:t.srclang,default:t.default,mode:t.track.mode,cues:[...t.track.cues].map(c=>({id:c.id,start:c.startTime,end:c.endTime,text:c.getCueAsHTML().textContent}))};});
 assert.equal(track.cues.length,segments.length,'Native cue count differs from measured segments');
 assert(track.default&&track.language==='en'&&track.mode==='showing','Default native captions unavailable');
 let elapsed=0,previous=0;
 const timing=track.cues.map((cue,index)=>{
  elapsed+=audio[index].duration_seconds;const end=Math.round(elapsed*1000)/1000;
  assert(Math.abs(cue.start-previous)<.00051&&Math.abs(cue.end-end)<.00051,'Native cue timing differs from cumulative measured WAV boundaries');
  assert(cue.text===narration[index].replace(/[\r\n\t]+/g,' '),'Native cue text differs from exact source narration');
  const value={start:cue.start,end:cue.end};previous=end;return value;
 });
 assert(Math.abs(elapsed-manifest.duration_seconds)<=.25,'Caption/audio alignment exceeds declared rounding bound');
 row.caption_metadata={cue_count:timing.length,timings:timing,audio_container_delta_seconds:manifest.duration_seconds-elapsed,
  exact_cue_text:true,default_showing:true,video_sha256:manifest.sha256};save();
 await page.waitForFunction(()=>{const v=document.querySelector('video[aria-label="Narrated attributed source briefing"]');return v?.textTracks[0]?.mode==='showing'&&v.textTracks[0].activeCues?.length>0;},null,{timeout:10000});
 // Freeze only the already user-started video for a bounded same-frame visual
 // comparison. The player controls are outside the sampled caption region.
 await video.evaluate(v=>v.pause());
 const frameTime=await video.evaluate(v=>v.currentTime);
 await page.getByRole('button',{name:'Hide captions',exact:true}).waitFor({state:'visible'});
 await page.getByRole('button',{name:'Hide captions',exact:true}).focus();await page.mouse.move(2,2);
 let sample=0;
 async function pixels(){
  await video.scrollIntoViewIfNeeded();const b=await video.boundingBox();assert(b&&b.height>90);
  const clip={x:Math.ceil(b.x+2),y:Math.ceil(b.y+5),width:Math.floor(b.width-4),height:Math.floor(b.height-52)};
  assert(clip.x>=0&&clip.y>=0&&clip.width>0&&clip.height>0,'Native caption image region unavailable');
  const encoded=await page.screenshot({clip,animations:'disabled'}),decoded=PNG.sync.read(encoded);
  if(process.env.CM_BRIEFING_DEBUG_FRAMES==='1')fs.writeFileSync(path.join(output,`${row.browser}-caption-${sample++}.png`),encoded);
  return digest(Buffer.concat([Buffer.from(`${decoded.width}x${decoded.height}:`),decoded.data]));
 }
 await page.waitForTimeout(2500);const onFirst=await pixels();await page.waitForTimeout(100);const onStable=await pixels();
 assert.equal(onFirst,onStable,'Paused video caption region did not stabilize');
 await page.getByRole('button',{name:'Hide captions',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('video[aria-label="Narrated attributed source briefing"]')?.textTracks[0]?.mode==='disabled');
 await page.mouse.move(2,2);await page.waitForTimeout(2500);const off=await pixels();assert.notEqual(onStable,off,'Caption toggle did not change rendered pixels above the native control bar');
 await page.getByRole('button',{name:'Show captions',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('video[aria-label="Narrated attributed source briefing"]')?.textTracks[0]?.mode==='showing');
 await page.mouse.move(2,2);await page.waitForTimeout(2500);const onRestored=await pixels();
 assert(Math.abs(await video.evaluate(v=>v.currentTime)-frameTime)<.001,'Caption probe altered paused video time');
 const pausedRestore=onRestored===onStable;
 row.paused_caption_restore={status:pausedRestore?'PASS':'FAIL',same_frame:true,native_mode:'showing'};
 if(!pausedRestore){
  const guidance=page.getByText('If captions do not appear while paused, resume playback to show them.',{exact:true});
  assert(await guidance.isVisible(),'Paused-caption repaint limitation has no user guidance');
  const prior=await video.evaluate(v=>v.currentTime),b=await video.boundingBox();
  await video.click({position:{x:b.width/2,y:b.height/2}});
  await page.waitForFunction(t=>{const v=document.querySelector('video[aria-label="Narrated attributed source briefing"]');return !v.paused&&v.currentTime>t+.75;},prior,{timeout:10000});
  assert.equal(await guidance.count(),0,'Paused-caption guidance did not clear on actual playing');
  await video.click({position:{x:b.width/2,y:b.height/2}});
  await page.waitForFunction(()=>document.querySelector('video[aria-label="Narrated attributed source briefing"]')?.paused);
  await page.mouse.move(2,2);await page.waitForTimeout(2500);const resumedOn=await pixels();
  await page.getByRole('button',{name:'Hide captions',exact:true}).click();
  await page.mouse.move(2,2);await page.waitForTimeout(2500);const resumedOff=await pixels();
  assert.notEqual(resumedOn,resumedOff,'Actual user resume did not restore rendered caption pixels');
  row.caption_user_resume={status:'PASS',native_user_play_and_pause:true,from_time:prior,to_time:await video.evaluate(v=>v.currentTime),guidance_visible_before:true,guidance_cleared_on_playing:true};
  row.engine_limitations=[{requirement:'Paused caption enable repaints without resuming',status:'FAIL',
   handling:'Exact transcript remains available; explicit guidance and actual user-resume paint recovery passed. No automatic play, seek or synthetic event was used.'}];
 }
 // Native TextTrack API changes (the state used by browser CC controls) must
 // propagate back to the ordinary accessible toggle; no events are fabricated.
 await video.evaluate(v=>v.textTracks[0].mode='disabled');
 await page.getByRole('button',{name:'Show captions',exact:true}).waitFor({state:'visible'});
 await page.getByRole('button',{name:'Show captions',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('video[aria-label="Narrated attributed source briefing"]')?.textTracks[0]?.mode==='showing');
 await page.getByRole('button',{name:'Hide captions',exact:true}).waitFor({state:'visible'});
 await page.getByText('Narration transcript',{exact:true}).click();
 const transcript=page.getByRole('region',{name:'Complete narration transcript',exact:true});
 const texts=await transcript.locator('li>p').allTextContents();
 assert(JSON.stringify(texts)===JSON.stringify(narration),'Complete transcript differs from exact narration');
 await transcript.focus();const before=await transcript.evaluate(n=>({top:n.scrollTop,height:n.clientHeight,scroll_height:n.scrollHeight}));
 await page.keyboard.press('PageDown');await page.waitForTimeout(250);
 const after=await transcript.evaluate(n=>n.scrollTop);
 assert(before.scroll_height<=before.height||after>before.top,'Complete transcript is not keyboard-scrollable');
 row.captions={cue_count:timing.length,timings:timing,audio_container_delta_seconds:manifest.duration_seconds-elapsed,
  transcript_sha256:digest(JSON.stringify(texts)),exact_transcript:true,default_showing:true,
  rendered_caption_on_off_pixels:true,paused_render_restore:pausedRestore,frame_time:frameTime,native_off_custom_on_state_sync:true,
  transcript_keyboard_scroll:{...before,after},pixel_buffers_retained:false,private_debug_frames_retained:process.env.CM_BRIEFING_DEBUG_FRAMES==='1',
  limits:'Segment boundaries, not word alignment. Native TextTrack API sync is not a test of every browser CC menu.'};
 row.checks.push('native_caption_cues_exact_text_measured_timings_and_visible_on_off_pixels');
 row.checks.push('exact_complete_transcript_keyboard_scroll_and_native_track_state_sync');
}
(async()=>{
 for(const [engine,type] of Object.entries({chromium,firefox,webkit})){
  const row={browser:engine,viewport:{width:390,height:844},status:'running',checks:[],page_errors:[],generation_posts:0};
  result.cases.push(row);save();let browser,context;const start=Date.now();
  try{
   browser=await type.launch({headless:true,args:engine==='chromium'?['--enable-unsafe-swiftshader']:[]});row.version=browser.version();
   context=await browser.newContext({viewport:row.viewport,hasTouch:true});
   const analysisResponse=await context.request.get(base+'/api/briefing/latest');assert(analysisResponse.ok());
   const analysis=await analysisResponse.json();assert.equal(analysis.status,'available');
   const source=analysis.reports.find(report=>report.id===expectedId);assert(source,'Expected actual source result unavailable');
   const videoResponse=await context.request.get(base+'/api/briefing/video/manifest');assert(videoResponse.ok());
   const manifest=await videoResponse.json();assert.equal(manifest.status,'available');
   assert(manifest.sources.some(source=>source.id===expectedId),'Video not bound to expected source');
   row.source_id=expectedId;row.video_sha256=manifest.sha256;
   const page=await context.newPage();
   page.on('pageerror',error=>row.page_errors.push(sanitize(error.message)));
   page.on('request',request=>{if(request.method()==='POST'&&/\/api\/briefing\/(?:analyze|video)$/.test(new URL(request.url()).pathname))row.generation_posts++;});
   await page.addInitScript(()=>localStorage.setItem('cm_seen_methods_v2','1'));
   await page.goto(base+'/?view=earth',{waitUntil:'domcontentloaded'});
   const canvas=page.locator('.cesium-widget canvas');await canvas.waitFor({state:'visible',timeout:30000});
   await page.waitForFunction(()=>document.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')==='ready',null,{timeout:40000});
   const handle=await canvas.elementHandle();
   const nav=page.locator('.mobile-bottom-nav');await nav.getByRole('button',{name:/Brief/}).click();
   await page.getByRole('group',{name:'Briefing tools'}).getByRole('button',{name:'Local analysis',exact:true}).click();
   const panel=page.locator('.local-briefing-panel');await panel.waitFor({state:'visible'});
   const card=panel.locator('strong').filter({hasText:`[src:${expectedId}]`});await card.waitFor({state:'visible'});await card.scrollIntoViewIfNeeded();
   const excerpt=panel.getByText('Source excerpt and reference',{exact:true});await excerpt.click();
   assert(await panel.locator('details p').evaluateAll((nodes,text)=>nodes.some(node=>node.textContent===text),source.text),'UI altered the validated original source excerpt');
   row.checks.push('actual_validated_source_id_and_exact_original_excerpt_visible');
   assert(await page.evaluate(node=>node===document.querySelector('.cesium-widget canvas'),handle),'Analysis panel remounted Earth');
   await nav.getByRole('button',{name:/Media/}).click();
   await page.getByRole('group',{name:'Media tools'}).getByRole('button',{name:'Narrated briefing',exact:true}).click();
   const video=page.locator('video[aria-label="Narrated attributed source briefing"]');await video.waitFor({state:'visible'});
   await video.scrollIntoViewIfNeeded();
   await page.waitForFunction(()=>{const v=document.querySelector('video[aria-label="Narrated attributed source briefing"]');return v&&v.readyState>=1;},null,{timeout:20000});
   const box=await video.boundingBox();assert(box&&box.width>0&&box.height>0);
   await video.click({position:{x:box.width/2,y:box.height/2}});row.native_play_taps=1;
   await page.waitForTimeout(500);
   if(await video.evaluate(element=>element.paused)){await video.click({position:{x:24,y:Math.max(10,box.height-18)}});row.native_play_taps++;}
   await page.waitForFunction(()=>{const v=document.querySelector('video[aria-label="Narrated attributed source briefing"]');return v&&v.currentTime>=1.5&&!v.paused;},null,{timeout:15000});
   row.playback=await video.evaluate(element=>({current_time:element.currentTime,duration:element.duration,
     paused:element.paused,ready_state:element.readyState,error:element.error?.code??null,
     h264_aac_support:element.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"')}));
   assert.equal(row.playback.error,null);assert(Math.abs(row.playback.duration-manifest.duration_seconds)<.5);
   row.checks.push('native_user_play_advances_actual_h264_aac_artifact');
   await verifyCaptions(page,video,manifest,row);
   assert(await page.evaluate(node=>node===document.querySelector('.cesium-widget canvas'),handle),'Video panel remounted Earth');
   assert.equal(row.generation_posts,0,'Viewing panel unexpectedly queued generation');
   assert.equal(row.page_errors.length,0,'Uncaught browser runtime error');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile panel horizontal overflow');
   row.checks.push('persistent_earth_no_implicit_jobs_and_mobile_layout');row.status=row.engine_limitations?.length?'qualified_with_limitations':'passed';
  }catch(error){row.status='failed';row.error=sanitize(error.message);}
  finally{row.seconds=(Date.now()-start)/1000;if(context)await context.close();if(browser)await browser.close();save();console.log(JSON.stringify({browser:engine,status:row.status,seconds:row.seconds,error:row.error}));}
 }
 result.ended_at=new Date().toISOString();result.passed=result.cases.filter(row=>row.status==='passed').length;
 result.qualified=result.cases.filter(row=>row.status==='passed'||row.status==='qualified_with_limitations').length;
 result.native_playback_passed=result.cases.filter(row=>row.playback&&!row.playback.paused&&row.playback.current_time>=1.5&&row.playback.error===null).length;
 result.paused_caption_restore_passed=result.cases.filter(row=>row.paused_caption_restore?.status==='PASS').length;
 result.status=result.qualified!==3?'findings_or_unavailable':result.passed===3?'passed':'qualified_with_caption_limitations';save();process.exitCode=result.qualified===3?0:1;
})().catch(error=>{result.status='observer_failed';result.error=sanitize(error.message);save();process.exitCode=1;});
