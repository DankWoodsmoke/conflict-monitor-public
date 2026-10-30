/* Bounded, read-only browser lifecycle observation. Never queues generation. */
const {chromium}=require('../frontend/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),cp=require('node:child_process'),crypto=require('node:crypto');
const base=process.env.CM_BASE_URL||'http://127.0.0.1:5190';
const output=process.env.CM_BROWSER_OUTPUT||'artifacts/browser-lifecycle';
const seconds=Number(process.env.CM_BROWSER_SECONDS||1800);
const longSession=process.env.CM_GOOGLE_LONG_SESSION==='1';
const stableProfile=longSession&&process.env.CM_REQUIRE_STABLE_PROFILE==='1';
if(!Number.isFinite(seconds)||seconds<60||seconds>(longSession?14400:3600))throw Error('Use a bounded observation: normally60–3600s; long-session mode up to14400s');
if(longSession&&seconds<10980)throw Error('A genuine Google long session requires at least10980s; short/accelerated runs cannot qualify');
if(longSession&&!/^sha256:[a-f0-9]{64}$/.test(process.env.CM_EXPECT_FRONTEND_IMAGE||''))throw Error('Bind long-session observation to an explicit frontend image');
if(stableProfile)for(const prefix of ['FRONTEND','BACKEND','DB']){
 if(!/^sha256:[a-f0-9]{64}$/.test(process.env[`CM_EXPECT_${prefix}_IMAGE`]||'')||!process.env[`CM_EXPECT_${prefix}_STARTED_AT`])throw Error('Stable-profile mode requires all3 explicit image/start identities');
}
if(fs.existsSync(path.join(output,'summary.json')))throw Error('Preserve prior observation; select a fresh output');
fs.mkdirSync(output,{recursive:true});
const summary={started_at:new Date().toISOString(),scope:'bounded_chromium_browser_lifecycle',requested_seconds:seconds,
  samples:0,findings:0,generation_posts:0,page_errors:[],status:'running',limitations:[
  'Desktop Chromium at1440x1000 is not a physical device or cross-engine long soak.',
  'Sampled heap/DOM counters do not prove an absence of memory leaks.',
  'Source truth, imagery capture dates and listener audibility are not certified.']};
const sanitize=value=>String(value).replace(/https?:\/\/[^\s"<>]+/g,'[provider URL omitted]').slice(0,500);
function save(){fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify(summary,null,2));}
function identities(){return cp.execFileSync('docker',['inspect','--format','{{.Name}} {{.Image}} {{.State.StartedAt}}','cmonitor-live-frontend-1','cmonitor-live-backend-1','cmonitor-live-db-1'],{encoding:'utf8',timeout:15000}).trim().split(/\r?\n/).map(line=>{const [name,image,started_at]=line.split(' ');return{name,image,started_at};});}
// Runs in the browser. Never return cue text or a Blob/provider URL to receipts.
function captionMetrics(video){
 const element=video.querySelector('track[kind="captions"]'),tracks=video.textTracks;
 if(!element||element.readyState!==2||tracks.length!==1)throw Error('Narration caption track did not finish loading');
 const track=tracks[0],cues=Array.from(track.cues||[]);
 if(track.kind!=='captions'||track.mode!=='showing'||cues.length<3||cues.length>6)throw Error('Narration captions unavailable or not showing');
 let previous=0;
 const timings=cues.map(cue=>{
  if(!Number.isFinite(cue.startTime)||!Number.isFinite(cue.endTime)||cue.startTime<previous||cue.endTime<=cue.startTime||cue.endTime>245||typeof cue.text!=='string'||!cue.text.trim())throw Error('Narration caption cue boundaries or content invalid');
  previous=cue.endTime;return {start_seconds:cue.startTime,end_seconds:cue.endTime};
 });
 return {track_count:tracks.length,ready_state:element.readyState,mode:track.mode,cue_count:cues.length,timings};
}
(async()=>{
 let browser,context;const start=Date.now(),startMono=performance.now(),elapsed=()=>longSession?(performance.now()-startMono)/1000:(Date.now()-start)/1000;let firstRootMono=null,baselineGeneration=null,lastSampleMono=null;const actions=new Set();
 try{
  if(longSession){
   summary.scope=stableProfile?'genuine_google_long_session_stable_profile':'genuine_google_long_session_frontend_only';summary.identities_before=identities();
   assert.equal(summary.identities_before[0].image,process.env.CM_EXPECT_FRONTEND_IMAGE,'Frontend image does not match admission');
   if(process.env.CM_EXPECT_FRONTEND_STARTED_AT)assert.equal(summary.identities_before[0].started_at,process.env.CM_EXPECT_FRONTEND_STARTED_AT,'Frontend start differs from admission');
   if(stableProfile)for(const [index,prefix]of [[1,'BACKEND'],[2,'DB']]){
    assert.equal(summary.identities_before[index].image,process.env[`CM_EXPECT_${prefix}_IMAGE`],`${prefix} image differs from admission`);
    assert.equal(summary.identities_before[index].started_at,process.env[`CM_EXPECT_${prefix}_STARTED_AT`],`${prefix} start differs from admission`);
   }
   summary.source_hashes=Object.fromEntries(['tools/observe_browser_lifecycle.cjs','frontend/src/hooks/useGoogleEarthSession.ts','frontend/src/components/CesiumView.tsx','frontend/src/components/LocalBriefingPanel.tsx','frontend/src/lib/briefingCaptions.ts'].map(file=>[file,crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')]));
   summary.root_requests=[];summary.root_response_statuses=[];summary.child_requests_after_three_hours=0;summary.child_successes_after_three_hours=0;summary.backend_database_transitions=[];summary.camera_actions=[];
   summary.limitations.push(stableProfile?'All3 frontend/backend/database image and start identities are admitted explicitly and must remain unchanged. This browser sample does not replace the separate SQL/raw-source full-pipeline gate.':'This window binds the frontend only. Any backend/database transition is recorded separately and cannot qualify a continuous unchanged full pipeline.','No clock or runtime rotation interval is changed; no refresh button is activated.','Natural fresh-root handoff and successful new tile responses after three hours are required, not merely a cached static scene.');save();
  }
  browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});summary.version=browser.version();
  context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();
  page.on('pageerror',error=>summary.page_errors.push(sanitize(error.message)));
  page.on('request',request=>{if(request.method()==='POST'&&/\/api\/briefing\/(?:analyze|video)$/.test(new URL(request.url()).pathname))summary.generation_posts++;});
  if(longSession){
   page.on('request',request=>{const u=new URL(request.url());if(u.hostname!=='tile.googleapis.com')return;if(u.pathname==='/v1/3dtiles/root.json'){firstRootMono??=performance.now();summary.root_requests.push({at:new Date().toISOString(),elapsed_seconds:elapsed()});}else if(firstRootMono!==null&&performance.now()-firstRootMono>=10800000)summary.child_requests_after_three_hours++;});
   page.on('response',response=>{const u=new URL(response.url());if(u.hostname!=='tile.googleapis.com')return;if(u.pathname==='/v1/3dtiles/root.json')summary.root_response_statuses.push({elapsed_seconds:elapsed(),status:response.status()});else if(firstRootMono!==null&&performance.now()-firstRootMono>=10800000&&response.status()>=200&&response.status()<300)summary.child_successes_after_three_hours++;});
  }
  await page.addInitScript(()=>localStorage.setItem('cm_seen_methods_v2','1'));
  await page.goto(base+'/?view=earth',{waitUntil:'domcontentloaded'});
  const canvas=page.locator('.cesium-widget canvas');await canvas.waitFor({state:'visible',timeout:30000});
  await page.waitForFunction(()=>document.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')==='ready',null,{timeout:40000});
  const handle=await canvas.elementHandle();
  const cdp=await context.newCDPSession(page);await cdp.send('Performance.enable');
  while(elapsed()<seconds){
   const tick=performance.now(),row={at:new Date().toISOString(),elapsed_seconds:elapsed(),findings:[]};
   try{
    if(longSession){
     if(lastSampleMono!==null)assert((tick-lastSampleMono)/1000<90,'Observation sample gap exceeded90s; host suspension is not continuous coverage');lastSampleMono=tick;
     row.identities=identities();assert.deepEqual(row.identities[0],summary.identities_before[0],'Frontend identity changed');
     const previous=summary.backend_database_transitions.at(-1)?.identities||summary.identities_before.slice(1);
     if(JSON.stringify(previous)!==JSON.stringify(row.identities.slice(1)))summary.backend_database_transitions.push({at:row.at,elapsed_seconds:row.elapsed_seconds,identities:row.identities.slice(1)});
     if(stableProfile)assert.deepEqual(row.identities,summary.identities_before,'Stable frontend/backend/database identity changed');
     for(const [at,name]of [[30,'Dubai'],[8700,'Tehran'],[9480,'Dubai'],[10860,'Tel Aviv']])if(row.elapsed_seconds>=at&&!actions.has(at)){
      await page.getByRole('navigation',{name:'Workspace views'}).getByRole('button',{name:/^Earth —/}).click();
      const toggle=page.locator('.earth-navigation-toggle');if(await toggle.getAttribute('aria-expanded')==='false')await toggle.click();
      await page.getByRole('group',{name:'Reference city views'}).getByRole('button',{name,exact:true}).click();actions.add(at);summary.camera_actions.push({elapsed_seconds:elapsed(),reference_city:name});
     }
    }
    const mode=summary.samples%3;
    const nav=page.getByRole('navigation',{name:'Workspace views'});
    if(mode===0)await nav.getByRole('button',{name:/^Earth —/}).click();
    else if(mode===1){
      await nav.getByRole('button',{name:/^Situation brief —/}).click();
      await page.getByRole('group',{name:'Briefing tools'}).getByRole('button',{name:'Local analysis',exact:true}).click();
      await page.locator('.local-briefing-panel').waitFor({state:'visible'});
    }else{
      await nav.getByRole('button',{name:/^Media —/}).click();
      await page.getByRole('group',{name:'Media tools'}).getByRole('button',{name:'Narrated briefing',exact:true}).click();
      await page.locator('video[aria-label="Narrated attributed source briefing"]').waitFor({state:'visible'});
      if(longSession){
       await page.waitForFunction(()=>{const video=document.querySelector('video[aria-label="Narrated attributed source briefing"]');return video?.querySelector('track[kind="captions"]')?.readyState===2&&video.textTracks.length===1;},null,{timeout:15000});
       row.captions=await page.locator('video[aria-label="Narrated attributed source briefing"]').evaluate(captionMetrics);
      }
    }
    row.workspace=['earth','local_analysis','narrated_briefing'][mode];
    assert(await page.evaluate(node=>node===document.querySelector('.cesium-widget canvas'),handle),'Earth canvas remounted');
    // Panel resizing can legitimately refine a different tile set. Require
    // bounded actual readiness before sampling instead of treating root-load
    // success as a permanent provider-ready state.
    const providerWait=Date.now();
    await page.waitForFunction(()=>document.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')==='ready',null,{timeout:40000});
    row.provider_settle_milliseconds=Date.now()-providerWait;
    row.scene=await page.locator('.earth-workspace').evaluate(element=>({provider:element.getAttribute('data-earth-provider'),
      canvas_count:element.querySelectorAll('.cesium-widget canvas').length,
      positions:Number(element.querySelector('.earth-coverage')?.getAttribute('data-position-count')),
      last_known:Number(element.querySelector('.earth-coverage')?.getAttribute('data-last-known-count'))}));
    if(longSession){
     row.session=await page.locator('.earth-workspace').evaluate(element=>({phase:element.dataset.earthSession,generation:Number(element.dataset.earthSessionGeneration),attempt:Number(element.dataset.earthSessionAttempt),root_at:Number(element.dataset.earthSessionRootAt),retries:Number(element.dataset.earthSessionRetries),visibility:document.visibilityState,attribution_visible:!!element.querySelector('.earth-attribution')&&element.querySelector('.earth-attribution').getBoundingClientRect().height>0}));
     assert.equal(row.session.visibility,'visible','Hidden tab cannot qualify foreground rendering');assert(row.session.attribution_visible,'Native attribution disappeared');assert(Number.isFinite(row.session.generation)&&row.session.generation>=1,'Session diagnostics unavailable');
     baselineGeneration??=row.session.generation;
     if(row.session.generation>baselineGeneration&&!summary.natural_rotation){assert(firstRootMono!==null&&(performance.now()-firstRootMono)>=8998000,'Unexpected early fresh-root handoff');summary.natural_rotation={at:row.at,elapsed_seconds:elapsed(),generation:row.session.generation,root_at:row.session.root_at};}
    }
    assert.equal(row.scene.canvas_count,1,'Unexpected renderer count');assert.equal(row.scene.provider,'ready','Google provider changed state');
    const performanceMetrics=await cdp.send('Performance.getMetrics');
    row.heap=Object.fromEntries(performanceMetrics.metrics.filter(metric=>['JSHeapUsedSize','JSHeapTotalSize'].includes(metric.name)).map(metric=>[metric.name,metric.value]));
    row.dom=await cdp.send('Memory.getDOMCounters');
    assert.equal(summary.generation_posts,0,'Viewing unexpectedly queued model/video work');
    assert.equal(summary.page_errors.length,0,'Uncaught browser error');
   }catch(error){row.findings.push(sanitize(error.message));summary.findings++;}
   summary.samples++;summary.elapsed_seconds=elapsed();
   fs.appendFileSync(path.join(output,'samples.jsonl'),JSON.stringify(row)+'\n');save();
   const delay=Math.min(30000-(performance.now()-tick),(seconds-elapsed())*1000);
   if(delay>0)await new Promise(resolve=>setTimeout(resolve,delay));
  }
  if(longSession){
   summary.identities_after=identities();assert.deepEqual(summary.identities_after[0],summary.identities_before[0],'Final frontend identity changed');
   if(stableProfile)assert.deepEqual(summary.identities_after,summary.identities_before,'Final stable-profile identity changed');
   assert(firstRootMono!==null&&performance.now()-firstRootMono>=10800000,'Less than three real hours since initial root request');assert(summary.natural_rotation,'No observed natural150-minute root handoff');
   assert(summary.root_requests.length>=2,'No fresh root network request');assert(summary.root_response_statuses.every(row=>row.status===200),'Google root response failed');
   assert(summary.child_requests_after_three_hours>0&&summary.child_successes_after_three_hours>0,'No successful fresh Google tile network work after three hours');
   assert(actions.has(10860),'Post-three-hour reference-city exploration was not exercised');
  }
  summary.status=summary.findings?'completed_with_findings':'completed_sample';
 }catch(error){summary.status='observer_failed';summary.error=sanitize(error.message);}
 finally{if(context)await context.close();if(browser)await browser.close();summary.ended_at=new Date().toISOString();summary.elapsed_seconds=elapsed();save();console.log(JSON.stringify(summary));if(longSession&&(summary.status!=='completed_sample'||summary.findings))process.exitCode=1;}
})().catch(error=>{summary.status='observer_failed';summary.error=sanitize(error.message);save();process.exitCode=1;});
