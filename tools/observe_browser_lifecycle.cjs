/* Bounded, read-only browser lifecycle observation. Never queues generation. */
const {chromium}=require('../frontend/node_modules/playwright');
const {captureProjection,validatePublicScene,assertFinalSampleGap,createGoogleTileCounters}=require('./browser_public_projection.cjs');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),cp=require('node:child_process'),crypto=require('node:crypto');
const base=process.env.CM_BASE_URL||'http://127.0.0.1:5190';
const output=process.env.CM_BROWSER_OUTPUT||'artifacts/browser-lifecycle';
const seconds=Number(process.env.CM_BROWSER_SECONDS||1800);
const longSession=process.env.CM_GOOGLE_LONG_SESSION==='1';
const stableProfile=longSession&&process.env.CM_REQUIRE_STABLE_PROFILE==='1';
const artifactProfile=process.env.CM_BROWSER_DATA_PROFILE||'operator-artifacts';
if(!['operator-artifacts','operator-free','public-context'].includes(artifactProfile))throw Error('Unknown browser data profile');
const containerNames=['FRONTEND','BACKEND','DB'].map(prefix=>process.env[`CM_${prefix}_CONTAINER`]||`cmonitor-live-${prefix.toLowerCase()}-1`);
if(containerNames.some(name=>!/^[-a-zA-Z0-9_.]{1,128}$/.test(name))||new Set(containerNames).size!==3)throw Error('Explicit distinct container names required');
if(!Number.isFinite(seconds)||seconds<60||seconds>(longSession?14400:3600))throw Error('Use a bounded observation: normally60–3600s; long-session mode up to14400s');
if(longSession&&seconds<10980)throw Error('A genuine Google long session requires at least10980s; short/accelerated runs cannot qualify');
if(longSession&&!/^sha256:[a-f0-9]{64}$/.test(process.env.CM_EXPECT_FRONTEND_IMAGE||''))throw Error('Bind long-session observation to an explicit frontend image');
if(stableProfile)for(const prefix of ['FRONTEND','BACKEND','DB']){
 if(!/^sha256:[a-f0-9]{64}$/.test(process.env[`CM_EXPECT_${prefix}_IMAGE`]||'')||!process.env[`CM_EXPECT_${prefix}_STARTED_AT`])throw Error('Stable-profile mode requires all3 explicit image/start identities');
}
if(fs.existsSync(path.join(output,'summary.json')))throw Error('Preserve prior observation; select a fresh output');
fs.mkdirSync(output,{recursive:true});
const summary={started_at:new Date().toISOString(),scope:'bounded_chromium_browser_lifecycle',requested_seconds:seconds,
  samples:0,findings:0,generation_posts:0,page_errors:[],status:'running',artifact_profile:artifactProfile,limitations:[
  'Desktop Chromium at1440x1000 is not a physical device or cross-engine long soak.',
  'Sampled heap/DOM counters do not prove an absence of memory leaks.',
  'Source truth, imagery capture dates and listener audibility are not certified.']};
const sanitize=value=>String(value).replace(/https?:\/\/[^\s"<>]+/g,'[provider URL omitted]').slice(0,500);
function save(){fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify(summary,null,2));}
function identities(){return cp.execFileSync('docker',['inspect','--format','{{.Name}} {{.Image}} {{.State.StartedAt}}',...containerNames],{encoding:'utf8',timeout:15000}).trim().split(/\r?\n/).map(line=>{const [name,image,started_at]=line.split(' ');return{name,image,started_at};});}
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
 let browser,context;const start=Date.now(),startMono=performance.now(),elapsed=()=>longSession?(performance.now()-startMono)/1000:(Date.now()-start)/1000;let firstRootMono=null,baselineGeneration=null,lastSampleMono=null;const actions=new Set(),publicHistory={observations:[],aircraft:[]};
 try{
  if(longSession){
   summary.scope=stableProfile?'genuine_google_long_session_stable_profile':'genuine_google_long_session_frontend_only';summary.identities_before=identities();
   assert.equal(summary.identities_before[0].image,process.env.CM_EXPECT_FRONTEND_IMAGE,'Frontend image does not match admission');
   if(process.env.CM_EXPECT_FRONTEND_STARTED_AT)assert.equal(summary.identities_before[0].started_at,process.env.CM_EXPECT_FRONTEND_STARTED_AT,'Frontend start differs from admission');
   if(stableProfile)for(const [index,prefix]of [[1,'BACKEND'],[2,'DB']]){
    assert.equal(summary.identities_before[index].image,process.env[`CM_EXPECT_${prefix}_IMAGE`],`${prefix} image differs from admission`);
    assert.equal(summary.identities_before[index].started_at,process.env[`CM_EXPECT_${prefix}_STARTED_AT`],`${prefix} start differs from admission`);
   }
   summary.source_hashes=Object.fromEntries(['tools/observe_browser_lifecycle.cjs','tools/browser_public_projection.cjs','frontend/src/lib/publicSceneDiagnostics.ts','frontend/src/hooks/usePublicationPoll.ts','frontend/src/hooks/useGoogleEarthSession.ts','frontend/src/components/CesiumView.tsx','frontend/src/components/LocalBriefingPanel.tsx','frontend/src/lib/briefingCaptions.ts'].map(file=>[file,crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')]));
   summary.root_requests=[];summary.root_response_statuses=[];summary.child_requests_after_three_hours=0;summary.child_successes_after_three_hours=0;summary.backend_database_transitions=[];summary.camera_actions=[];
   summary.limitations.push(stableProfile?'All3 frontend/backend/database image and start identities are admitted explicitly and must remain unchanged. This browser sample does not replace the separate SQL/raw-source full-pipeline gate.':'This window binds the frontend only. Any backend/database transition is recorded separately and cannot qualify a continuous unchanged full pipeline.','No clock or runtime rotation interval is changed; no refresh button is activated.','Natural fresh-root handoff and successful new tile responses after three hours are required, not merely a cached static scene.');save();
  }
  browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});summary.version=browser.version();
  context=await browser.newContext({viewport:{width:1440,height:1000}});
  const configResponse=await context.request.get(base+'/api/config');assert.equal(configResponse.status(),200,'Deployment capabilities unavailable');
  const capabilities=await configResponse.json();assert.equal(capabilities.public_read_only===true,artifactProfile==='public-context','Browser profile does not match deployed access mode');
  if(artifactProfile!=='operator-artifacts')summary.limitations.push('This observation verifies explicit unavailable artifact states; it does not qualify AI generation, captions or video playback.');
  const page=await context.newPage();
  if(artifactProfile==='public-context'){
   assert.equal(capabilities.public_observations_enabled,true);assert.equal(capabilities.public_aircraft_enabled,true);
   summary.public_response_failures=0;summary.public_response_counts={observations:0,aircraft:0};summary.public_scene_max_counts={observations:0,aircraft:0};
   summary.limitations.push('Public diagnostics compare received source batches to synchronized Cesium anchors after a frame; this does not prove source ground truth or raster pixel correctness.');
   page.on('response',async response=>{
    const u=new URL(response.url());if(u.origin!==new URL(base).origin)return;
    const kind={'/api/publication/observations':'observations','/api/publication/aircraft':'aircraft'}[u.pathname];if(!kind)return;
    try{
     assert.equal(response.status(),200,'Public publication request failed');
     const snapshot=captureProjection(kind,await response.json(),Date.now());
     publicHistory[kind].push(snapshot);if(publicHistory[kind].length>4)publicHistory[kind].shift();
     summary.public_response_counts[kind]++;
    }catch{summary.public_response_failures++;}
   });
  }
  const samplePublicScene=async()=>{
   const deadline=performance.now()+10000;let failure;
   do{
    try{
     const diagnostic=await page.locator('.earth-workspace').evaluate(node=>JSON.parse(node.getAttribute('data-public-scene')||'null'));
     return validatePublicScene(diagnostic,publicHistory,Date.now());
    }catch(error){failure=error;await page.waitForTimeout(250);}
   }while(performance.now()<deadline);
   throw failure;
  };
  page.on('pageerror',error=>summary.page_errors.push(sanitize(error.message)));
  page.on('request',request=>{
   const pathname=new URL(request.url()).pathname;
   if(request.method()==='POST'&&/^\/api\/(?:briefing\/(?:analyze|video)|report-analysis\/\d+)\/?$/.test(pathname))summary.generation_posts++;
  });
  if(longSession){
   const tiles=createGoogleTileCounters();
   const saveTileCounts=()=>{Object.assign(summary,{child_requests_total:tiles.counts.requests_total,child_responses_total:tiles.counts.responses_total,
    child_requests_after_three_hours:tiles.counts.requests_after_cutoff,child_successful_responses_after_three_hours_raw:tiles.counts.successful_responses_after_cutoff_raw,
    child_successes_after_three_hours:tiles.counts.successful_requests_after_cutoff});};
   saveTileCounts();
   page.on('request',request=>{const u=new URL(request.url());if(u.hostname!=='tile.googleapis.com')return;if(u.pathname==='/v1/3dtiles/root.json'){firstRootMono??=performance.now();summary.root_requests.push({at:new Date().toISOString(),elapsed_seconds:elapsed()});}else{tiles.request(request,firstRootMono===null?null:performance.now()-firstRootMono);saveTileCounts();}});
   page.on('response',response=>{const u=new URL(response.url());if(u.hostname!=='tile.googleapis.com')return;if(u.pathname==='/v1/3dtiles/root.json')summary.root_response_statuses.push({elapsed_seconds:elapsed(),status:response.status()});else{tiles.response(response.request(),response.status(),firstRootMono===null?null:performance.now()-firstRootMono);saveTileCounts();}});
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
    if(lastSampleMono!==null)assert((tick-lastSampleMono)/1000<90,'Observation sample gap exceeded90s; host suspension is not continuous coverage');lastSampleMono=tick;
    if(longSession){
     row.identities=identities();assert.deepEqual(row.identities[0],summary.identities_before[0],'Frontend identity changed');
     const previous=summary.backend_database_transitions.at(-1)?.identities||summary.identities_before.slice(1);
     if(JSON.stringify(previous)!==JSON.stringify(row.identities.slice(1)))summary.backend_database_transitions.push({at:row.at,elapsed_seconds:row.elapsed_seconds,identities:row.identities.slice(1)});
     if(stableProfile)assert.deepEqual(row.identities,summary.identities_before,'Stable frontend/backend/database identity changed');
     for(const [at,name]of [[30,'Dubai'],[8700,'Tehran'],[9480,'Dubai'],[10860,'Tel Aviv']])if(row.elapsed_seconds>=at&&!actions.has(at)){
      await page.getByRole('navigation',{name:'Workspace views'}).getByRole('button',{name:/^Earth —/}).click();
      const toggle=page.locator('.earth-navigation-toggle');if(await toggle.getAttribute('aria-expanded')==='false')await toggle.click();
      const cityDisclosure=page.locator('.earth-explore-details');
      if(await cityDisclosure.count()&&await cityDisclosure.getAttribute('open')===null)await cityDisclosure.locator(':scope > summary').click();
      await page.getByRole('group',{name:'Reference city views'}).getByRole('button',{name,exact:true}).click();actions.add(at);summary.camera_actions.push({elapsed_seconds:elapsed(),reference_city:name});
     }
    }
    const mode=summary.samples%3;
    const nav=page.getByRole('navigation',{name:'Workspace views'});
    if(mode===0)await nav.getByRole('button',{name:/^Earth —/}).click();
    else if(mode===1){
      await nav.getByRole('button',{name:/^Situation brief —/}).click();
      if(artifactProfile==='public-context')await page.locator('.public-empty-state').getByRole('heading',{name:'Briefings are not published',exact:true}).waitFor({state:'visible'});
      else{
      await page.getByRole('group',{name:'Briefing tools'}).getByRole('button',{name:'Local analysis',exact:true}).click();
      await page.locator('.local-briefing-panel').waitFor({state:'visible'});
      if(artifactProfile==='operator-free')await page.getByText('No validated local result yet. Viewing this panel does not start analysis.',{exact:true}).waitFor({state:'visible'});
      }
    }else{
      await nav.getByRole('button',{name:/^Media —/}).click();
      if(artifactProfile==='public-context')await page.locator('.public-empty-state').getByRole('heading',{name:'Media is not published',exact:true}).waitFor({state:'visible'});
      else{
      await page.getByRole('group',{name:'Media tools'}).getByRole('button',{name:'Narrated briefing',exact:true}).click();
      if(artifactProfile==='operator-free')await page.getByText('No validated narrated video yet. A failed render never substitutes a demonstration or an incomplete file.',{exact:true}).waitFor({state:'visible'});
      else{
      await page.locator('video[aria-label="Narrated attributed source briefing"]').waitFor({state:'visible'});
      if(longSession){
       await page.waitForFunction(()=>{const video=document.querySelector('video[aria-label="Narrated attributed source briefing"]');return video?.querySelector('track[kind="captions"]')?.readyState===2&&video.textTracks.length===1;},null,{timeout:15000});
       row.captions=await page.locator('video[aria-label="Narrated attributed source briefing"]').evaluate(captionMetrics);
      }
      }
      }
    }
    row.workspace=['earth','brief','media'][mode];row.artifact_profile=artifactProfile;
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
    if(artifactProfile==='public-context'){
     assert.equal(summary.public_response_failures,0,'Public publication request/response failed during observation');
     row.public_scene=await samplePublicScene();
     for(const kind of ['observations','aircraft'])summary.public_scene_max_counts[kind]=Math.max(summary.public_scene_max_counts[kind],row.public_scene[kind].count);
    }
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
  assertFinalSampleGap(performance.now()/1000,lastSampleMono===null?NaN:lastSampleMono/1000);
  if(artifactProfile==='public-context'){
   assert.equal(summary.public_response_failures,0,'Final public response failure');
   assert(Object.values(summary.public_scene_max_counts).every(count=>count>0),'No actual public dataset positions observed');
   summary.final_public_scene=await samplePublicScene();
  }
  if(longSession){
   summary.identities_after=identities();assert.deepEqual(summary.identities_after[0],summary.identities_before[0],'Final frontend identity changed');
   if(stableProfile)assert.deepEqual(summary.identities_after,summary.identities_before,'Final stable-profile identity changed');
   assert(firstRootMono!==null&&performance.now()-firstRootMono>=10800000,'Less than three real hours since initial root request');assert(summary.natural_rotation,'No observed natural150-minute root handoff');
   assert(summary.root_requests.length>=2,'No fresh root network request');assert(summary.root_response_statuses.every(row=>row.status===200),'Google root response failed');
   assert(summary.child_requests_after_three_hours>0&&summary.child_successes_after_three_hours>0,'No successful fresh Google tile network work after three hours');
   assert(actions.has(10860),'Post-three-hour reference-city exploration was not exercised');
  }
  assertFinalSampleGap(performance.now()/1000,lastSampleMono===null?NaN:lastSampleMono/1000);
  summary.status=summary.findings?'completed_with_findings':'completed_sample';
 }catch(error){summary.status='observer_failed';summary.error=sanitize(error.message);}
 finally{if(context)await context.close();if(browser)await browser.close();summary.ended_at=new Date().toISOString();summary.elapsed_seconds=elapsed();save();console.log(JSON.stringify(summary));if(summary.status!=='completed_sample'||summary.findings)process.exitCode=1;}
})().catch(error=>{summary.status='observer_failed';summary.error=sanitize(error.message);save();process.exitCode=1;});
