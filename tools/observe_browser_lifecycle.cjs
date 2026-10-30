/* Bounded, read-only browser lifecycle observation. Never queues generation. */
const {chromium}=require('../frontend/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const base=process.env.CM_BASE_URL||'http://127.0.0.1:5190';
const output=process.env.CM_BROWSER_OUTPUT||'artifacts/browser-lifecycle';
const seconds=Number(process.env.CM_BROWSER_SECONDS||1800);
if(!Number.isFinite(seconds)||seconds<60||seconds>3600)throw Error('Use a bounded 60–3600 second observation');
if(fs.existsSync(path.join(output,'summary.json')))throw Error('Preserve prior observation; select a fresh output');
fs.mkdirSync(output,{recursive:true});
const summary={started_at:new Date().toISOString(),scope:'bounded_chromium_browser_lifecycle',requested_seconds:seconds,
  samples:0,findings:0,generation_posts:0,page_errors:[],status:'running',limitations:[
  'Desktop Chromium at1440x1000 is not a physical device or cross-engine long soak.',
  'Sampled heap/DOM counters do not prove an absence of memory leaks.',
  'Source truth, imagery capture dates and listener audibility are not certified.']};
const sanitize=value=>String(value).replace(/https?:\/\/[^\s"<>]+/g,'[provider URL omitted]').slice(0,500);
function save(){fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify(summary,null,2));}
(async()=>{
 let browser,context;const start=Date.now();
 try{
  browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});summary.version=browser.version();
  context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();
  page.on('pageerror',error=>summary.page_errors.push(sanitize(error.message)));
  page.on('request',request=>{if(request.method()==='POST'&&/\/api\/briefing\/(?:analyze|video)$/.test(new URL(request.url()).pathname))summary.generation_posts++;});
  await page.addInitScript(()=>localStorage.setItem('cm_seen_methods_v2','1'));
  await page.goto(base+'/?view=earth',{waitUntil:'domcontentloaded'});
  const canvas=page.locator('.cesium-widget canvas');await canvas.waitFor({state:'visible',timeout:30000});
  await page.waitForFunction(()=>document.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')==='ready',null,{timeout:40000});
  const handle=await canvas.elementHandle();
  const cdp=await context.newCDPSession(page);await cdp.send('Performance.enable');
  while((Date.now()-start)/1000<seconds){
   const tick=Date.now(),row={at:new Date().toISOString(),elapsed_seconds:(tick-start)/1000,findings:[]};
   try{
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
    assert.equal(row.scene.canvas_count,1,'Unexpected renderer count');assert.equal(row.scene.provider,'ready','Google provider changed state');
    const performance=await cdp.send('Performance.getMetrics');
    row.heap=Object.fromEntries(performance.metrics.filter(metric=>['JSHeapUsedSize','JSHeapTotalSize'].includes(metric.name)).map(metric=>[metric.name,metric.value]));
    row.dom=await cdp.send('Memory.getDOMCounters');
    assert.equal(summary.generation_posts,0,'Viewing unexpectedly queued model/video work');
    assert.equal(summary.page_errors.length,0,'Uncaught browser error');
   }catch(error){row.findings.push(sanitize(error.message));summary.findings++;}
   summary.samples++;summary.elapsed_seconds=(Date.now()-start)/1000;
   fs.appendFileSync(path.join(output,'samples.jsonl'),JSON.stringify(row)+'\n');save();
   const delay=Math.min(30000-(Date.now()-tick),seconds*1000-(Date.now()-start));
   if(delay>0)await new Promise(resolve=>setTimeout(resolve,delay));
  }
  summary.status=summary.findings?'completed_with_findings':'completed_sample';
 }catch(error){summary.status='observer_failed';summary.error=sanitize(error.message);}
 finally{if(context)await context.close();if(browser)await browser.close();summary.ended_at=new Date().toISOString();summary.elapsed_seconds=(Date.now()-start)/1000;save();console.log(JSON.stringify(summary));}
})().catch(error=>{summary.status='observer_failed';summary.error=sanitize(error.message);save();process.exitCode=1;});
