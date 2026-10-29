/* Actual browser viewport/touch emulation. No trace, HAR, video, screenshots,
 * browser storage snapshots, public key or provider request URLs are emitted. */
const {chromium,firefox,webkit}=require('../frontend/node_modules/playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const base=process.env.CM_BASE_URL||'http://127.0.0.1:5190';
const output=process.env.CM_MOBILE_OUTPUT||'artifacts/mobile-earth';
const engines=(process.env.CM_ENGINES||'chromium,firefox,webkit').split(',');
const viewports=[{width:320,height:740},{width:390,height:844},{width:768,height:1024},{width:844,height:390}];
const sanitize=value=>String(value).replace(/https?:\/\/[^\s"<>]+/g,'[provider URL omitted]').replace(/([?&]key=)[^\s&]+/g,'$1[redacted]').slice(0,700);
const receipt={started_at:new Date().toISOString(),base_url:base,scope:'browser_viewport_and_touch_emulation',cases:[],limitations:[
  'Desktop browser engines with emulated viewport/touch are not physical iOS or Android devices.',
  'Tiles, imagery dates and source reports are not ground truth or incident confirmation.',
  'No arbitrary external media playback or long-term GPU reliability is certified.']};
fs.mkdirSync(output,{recursive:true});
function save(){fs.writeFileSync(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2));}
async function visible(locator){return locator.count()&&await locator.first().isVisible();}
async function selectTab(page,name){
 const mobile=page.locator('.mobile-bottom-nav');
 if(await visible(mobile))await mobile.getByRole('button',{name:new RegExp(name)}).click();
 else await page.getByRole('navigation',{name:'Workspace views'}).getByRole('button',{name:new RegExp(`^(?:${name==='Brief'?'Situation brief':name}) —`)}).click();
}
async function checkLayout(page,label){
 const layout=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
   height:innerHeight,scrollHeight:document.documentElement.scrollHeight}));
 assert(layout.scrollWidth<=layout.width+1,`${label}: horizontal page overflow ${layout.scrollWidth}/${layout.width}`);
 return layout;
}
(async()=>{
 for(const name of engines){
  let browser;
  try{browser=await({chromium,firefox,webkit}[name]).launch({headless:true,args:name==='chromium'?['--enable-unsafe-swiftshader']:[]});}
  catch(error){receipt.cases.push({browser:name,status:'runtime_unavailable',error:sanitize(error.message)});save();continue;}
  for(const viewport of viewports){
   const row={browser:name,version:browser.version(),viewport,status:'running',checks:[],page_errors:[]};
   receipt.cases.push(row);save();const start=Date.now();
   const context=await browser.newContext({viewport,hasTouch:true,deviceScaleFactor:1});
   const page=await context.newPage();
   page.on('pageerror',error=>row.page_errors.push(sanitize(error.message)));
   try{
    await page.addInitScript(()=>localStorage.setItem('cm_seen_methods_v2','1'));
    await page.goto(base+'/?view=earth',{waitUntil:'domcontentloaded',timeout:30000});
    await page.locator('header h1').first().waitFor({timeout:20000});
    const dismiss=page.getByRole('button',{name:/close.*(?:about|methods)|begin monitoring/i});
    if(await visible(dismiss))await dismiss.first().click();
    const workspace=page.locator('.earth-workspace');await workspace.waitFor({timeout:30000});
    const canvas=page.locator('.cesium-widget canvas');await canvas.waitFor({state:'visible',timeout:30000});
    const handle=await canvas.elementHandle();
    await page.waitForFunction(()=>document.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')==='ready',null,{timeout:40000});
    assert((await page.locator('.cesium-widget-credits').innerText()).includes('Google'),'Google credit absent');
    row.checks.push('actual_google_tiles_connected_with_attribution');
    row.layout=await checkLayout(page,'Earth');
    for(const name of ['Media','Brief','Earth','Media','Earth']){
      await selectTab(page,name);
      if(name!=='Earth')await page.locator('.workspace-panel').waitFor({state:'visible'});
      assert(await page.evaluate(node=>node===document.querySelector('.cesium-widget canvas'),handle),'Earth canvas remounted during panel transition');
      await checkLayout(page,name);
    }
    row.checks.push('all_three_workspaces_fit_and_preserve_same_earth_canvas');
    const search=page.locator('#earth-search');
    await search.fill('91,181');
    await page.getByText('No known position matches.',{exact:false}).waitFor({state:'visible',timeout:5000});
    assert.equal(await page.getByRole('button',{name:/^Coordinates/}).count(),0,'Out-of-range coordinates were offered as a position');
    await search.fill('0,0');
    await page.getByRole('button',{name:/^Coordinates/}).waitFor({state:'visible',timeout:5000});
    await search.fill('');row.checks.push('coordinate_bounds_and_zero_position');
    if(viewport.width===390){
      const coverage=page.locator('.earth-coverage');
      assert(Number(await coverage.getAttribute('data-position-count'))>0,'No real positions available for hemisphere qualification');
      await search.fill('0,180');await page.getByRole('button',{name:'Go',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('.earth-coverage')?.getAttribute('data-visible-count')==='0',null,{timeout:10000});
      await page.getByRole('button',{name:'Region',exact:true}).click();
      await page.waitForFunction(()=>Number(document.querySelector('.earth-coverage')?.getAttribute('data-visible-count'))>0,null,{timeout:10000});
      row.checks.push('actual_farside_positions_hidden_and_region_restores_visible_hemisphere');
    }
    await page.getByRole('button',{name:/^Layers/}).click();
    await page.locator('.earth-layer-panel').waitFor({state:'visible'});
    await checkLayout(page,'Layers');
    const aging=page.getByRole('checkbox',{name:'Show last-known positions',exact:true});
    assert(await aging.isChecked(),'Last-known positions should be enabled with their distinct aging state');
    row.position_counts=await page.locator('.earth-coverage').evaluate(element=>({
      enabled:Number(element.getAttribute('data-position-count')),visible:Number(element.getAttribute('data-visible-count')),
      last_known:Number(element.getAttribute('data-last-known-count'))}));
    assert(Number.isInteger(row.position_counts.last_known)&&row.position_counts.last_known>=0,'Missing actual aging-position count');
    await aging.uncheck();
    await page.waitForFunction(()=>document.querySelector('.earth-coverage')?.getAttribute('data-last-known-count')==='0');
    await aging.check();row.checks.push('last_known_position_count_and_optional_aging_visibility_control');
    const layerClose=page.getByRole('button',{name:/Close (?:spatial )?layers/i});
    if(await visible(layerClose))await layerClose.click();else await page.getByRole('button',{name:/^Layers/}).click();
    await page.getByRole('button',{name:'Settings',exact:true}).click();
    await page.getByRole('dialog').waitFor({state:'visible'});await checkLayout(page,'Settings');
    await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'hidden'});
    row.checks.push('layer_and_settings_dialog_layout_and_keyboard_dismissal');
    const response=await context.request.get(base+'/api/status');
    assert(response.ok(),'Production provider status unavailable');
    const provider=(await response.json()).aircraft;
    row.aircraft_coverage={status:provider.status,source:provider.source,count:provider.count,
      region_count:Array.isArray(provider.regions)?provider.regions.length:Object.keys(provider.regions||{}).length};
    assert(row.aircraft_coverage.count>0&&row.aircraft_coverage.region_count===4,'Expected four-region live aircraft coverage unavailable');
    row.checks.push('actual_four_region_aircraft_cache_available');
    row.google_provider_end_state=await workspace.getAttribute('data-earth-provider');
    assert.equal(row.page_errors.length,0,'Uncaught browser runtime errors');
    row.status='passed';
   }catch(error){row.status='failed';row.error=sanitize(error.message);}
   finally{row.seconds=(Date.now()-start)/1000;await context.close();save();console.log(JSON.stringify({browser:name,viewport,status:row.status,seconds:row.seconds,error:row.error}));}
  }
  await browser.close();
 }
 receipt.ended_at=new Date().toISOString();
 receipt.passed=receipt.cases.filter(row=>row.status==='passed').length;
 receipt.failed=receipt.cases.filter(row=>row.status!=='passed').length;
 receipt.status=receipt.failed?'findings_or_unavailable':'passed';save();
 process.exitCode=receipt.failed?1:0;
})().catch(error=>{receipt.status='observer_failed';receipt.error=sanitize(error.message);save();process.exitCode=1;});
