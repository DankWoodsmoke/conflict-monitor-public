/* Native browser playback of the actual local artifact. Viewing never queues work. */
const {chromium,firefox,webkit}=require('../frontend/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
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
   assert(await page.evaluate(node=>node===document.querySelector('.cesium-widget canvas'),handle),'Video panel remounted Earth');
   assert.equal(row.generation_posts,0,'Viewing panel unexpectedly queued generation');
   assert.equal(row.page_errors.length,0,'Uncaught browser runtime error');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile panel horizontal overflow');
   row.checks.push('persistent_earth_no_implicit_jobs_and_mobile_layout');row.status='passed';
  }catch(error){row.status='failed';row.error=sanitize(error.message);}
  finally{row.seconds=(Date.now()-start)/1000;if(context)await context.close();if(browser)await browser.close();save();console.log(JSON.stringify({browser:engine,status:row.status,seconds:row.seconds,error:row.error}));}
 }
 result.ended_at=new Date().toISOString();result.passed=result.cases.filter(row=>row.status==='passed').length;
 result.status=result.passed===3?'passed':'findings_or_unavailable';save();process.exitCode=result.passed===3?0:1;
})().catch(error=>{result.status='observer_failed';result.error=sanitize(error.message);save();process.exitCode=1;});
