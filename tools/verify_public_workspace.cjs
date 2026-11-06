/* Real Google Earth in closed or explicitly admitted public profiles. No screenshots, HAR,
 * traces, storage, credentials, provider URLs or report payloads are emitted. */
const {chromium,firefox,webkit}=require('../frontend/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=new URL(process.env.CM_BASE_URL||'http://127.0.0.1:5197');
assert(['127.0.0.1','[::1]'].includes(base.hostname)&&['http:','https:'].includes(base.protocol)
  &&!base.username&&!base.password&&base.pathname==='/'&&!base.search&&!base.hash,'Use a credential-free literal loopback origin');
const output=process.env.CM_PUBLIC_WORKSPACE_OUTPUT||'artifacts/private/public-workspace';
const engines=(process.env.CM_ENGINES||'chromium,firefox,webkit').split(',');
assert(engines.every(name=>['chromium','firefox','webkit'].includes(name)),'Unknown browser engine');
const viewports=[{width:320,height:740},{width:390,height:844},{width:1440,height:900}];
const settleMs=35000; // Observe a complete status cycle and more than two tracking poll cycles.
const requirePublicData=process.env.CM_REQUIRE_PUBLIC_DATA==='1';
assert(!process.env.CM_REQUIRE_PUBLIC_DATA||['0','1'].includes(process.env.CM_REQUIRE_PUBLIC_DATA),'CM_REQUIRE_PUBLIC_DATA must be 0 or 1');
const sanitize=value=>String(value).replace(/https?:\/\/[^\s"<>]+/g,'[URL omitted]')
  .replace(/AIza[A-Za-z0-9_-]+/g,'[key omitted]').replace(/([?&](?:key|token|session)=)[^\s&]+/gi,'$1[omitted]').slice(0,500);
const receipt={started_at:new Date().toISOString(),scope:requirePublicData?'admitted_public_datasets_real_google_browser_emulation':'default_closed_public_profile_real_google_browser_emulation',
  cases:[],limitations:['Desktop Chromium/Firefox/WebKit with viewport and touch emulation are not physical iOS or Android devices.',
    'Imagery connectivity and attribution do not establish capture date, source accuracy or incident confirmation.',
    requirePublicData?'NASA thermal pixels and selected adsb.lol aircraft are source observations, not verified incidents or complete conflict coverage.':'No populated public dataset is admitted by this mode; configured publication endpoints must remain empty/unavailable.',
    'This finite observation is not a long-session soak or external hosting/capacity qualification.']};
function save(){fs.writeFileSync(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2));}
const isHash=value=>typeof value==='string'&&/^[0-9a-f]{64}$/.test(value);
function inspectPublication(data,kind,required,now=Date.now()){
  const nasa=kind==='observations',rows=nasa?data.hotspots:data.aircraft;
  assert.equal(data.source,nasa?'nasa_firms_noaa20':'adsb_lol','Unexpected public source');
  assert(Array.isArray(rows)&&rows.length<=(nasa?2000:5000),'Invalid or unbounded publication rows');
  assert(!['raw_text','reports','source_reports','telegram','private_reports'].some(key=>Object.hasOwn(data,key)),'Private fields in publication');
  if(!required){
    assert(['awaiting_publication','failed'].includes(data.status)&&data.batch_id===null&&rows.length===0,'Populated public datasets require CM_REQUIRE_PUBLIC_DATA=1');
    return {status:data.status,count:0};
  }
  assert.equal(data.status,'fresh','Required actual source dataset is not fresh');
  assert(rows.length>0,'Required actual source dataset is empty');
  assert(isHash(data.batch_id)&&Number.isFinite(Date.parse(data.published_at)),'Publication identity/clock missing');
  const identities=new Set(),positions=new Set();
  for(const row of rows){
    assert(typeof row.lat==='number'&&Number.isFinite(row.lat)&&Math.abs(row.lat)<=90&&typeof row.lon==='number'&&Number.isFinite(row.lon)&&Math.abs(row.lon)<=180,'Invalid source coordinate');
    const clock=Date.parse(nasa?row.ts:row.observed_at);
    assert(Number.isFinite(clock)&&clock<=now+300000&&now-clock<=(nasa?48*3600000:120000)+5000,'Source observation clock outside displayed window');
    assert(!['raw_text','reports','proximity_matches','summary','severity','aircraft_category','is_emergency'].some(key=>Object.hasOwn(row,key)),'Private or inferred field in public observation');
    if(nasa)assert(row.satellite==='NOAA-20'&&row.instrument==='VIIRS'&&row.frp>=10&&row.lat>=10&&row.lat<=42&&row.lon>=25&&row.lon<=65&&isHash(row.source_row_sha256),'NASA source/filter provenance missing');
    else assert(row.source==='adsb.lol'&&/^~?[0-9a-f]{6}$/.test(row.icao24)&&isHash(row.normalized_record_sha256),'Aircraft source provenance missing');
    const id=nasa?row.id:row.icao24;
    assert(!identities.has(id),'Duplicate public identity');identities.add(id);
    if(nasa){const key=JSON.stringify([row.lat,row.lon,clock]);assert(!positions.has(key),'Duplicate thermal position/time');positions.add(key);}
  }
  if(nasa)assert(data.displayed_count===rows.length&&data.eligible_count>=rows.length&&data.source_rows>=data.regional_rows,'NASA filter counts do not reconcile');
  else assert(data.license==='ODbL-1.0'&&data.license_url==='https://opendatacommons.org/licenses/odbl/1-0/'&&Array.isArray(data.coverage)&&data.coverage.length===4,'Aircraft license/coverage missing');
  return {status:data.status,count:rows.length,batch_id:data.batch_id,published_at:data.published_at};
}
function allowedApiPaths(config){
  return new Set(['/api/config','/api/status',...(config.public_observations_enabled===true?['/api/publication/observations']:[]),...(config.public_aircraft_enabled===true?['/api/publication/aircraft']:[])]);
}
async function visible(locator){return !!(await locator.count())&&await locator.first().isVisible();}
async function settleLayout(page){await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));await page.waitForTimeout(250);}
async function selectTab(page,name){
  const mobile=page.locator('.mobile-bottom-nav');
  if(await visible(mobile))await mobile.getByRole('button',{name:new RegExp(name,'i')}).click();
  else await page.getByRole('navigation',{name:'Workspace views'}).getByRole('button',{name:new RegExp(`^(?:${name==='Brief'?'Situation brief':name}) —`)}).click();
  await settleLayout(page);
}
async function checkLayout(page,label){
  const result=await page.evaluate(()=>{
    const selectors=['.app-header','.app-header button','.mobile-bottom-nav','.mobile-bottom-nav button',
      '.earth-navigation','.cesium-widget canvas','.workspace-panel','.workspace-panel button',
      '.public-empty-state','.feed-sheet','.source-status-dialog'];
    const boxes=[...document.querySelectorAll(selectors.join(','))].map(node=>{
      const r=node.getBoundingClientRect(),style=getComputedStyle(node);
      return {kind:node.tagName==='CANVAS'?'earth_canvas':node.classList[0]||node.tagName.toLowerCase(),
        left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height,
        visible:style.display!=='none'&&style.visibility!=='hidden'&&r.width>0&&r.height>0};
    }).filter(r=>r.visible);
    return {width:innerWidth,height:innerHeight,scroll_width:document.documentElement.scrollWidth,
      clipped:boxes.filter(r=>r.left< -1||r.right>innerWidth+1),box_count:boxes.length};
  });
  assert(result.scroll_width<=result.width+1,`${label}: horizontal page overflow`);
  assert.equal(result.clipped.length,0,`${label}: visible workspace controls exceed viewport`);
  return {width:result.width,height:result.height,scroll_width:result.scroll_width,checked_boxes:result.box_count};
}
async function checkAttribution(page){
  const link=page.locator('.earth-attribution .cesium-credit-expand-link');
  await link.waitFor({state:'visible'});
  const uncovered=await link.evaluate(node=>{
    const range=document.createRange();range.selectNodeContents(node);
    const rects=[...range.getClientRects()].filter(r=>r.width&&r.height);
    return rects.length>0&&rects.every(r=>{const top=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return top&&(top===node||node.contains(top));});
  });
  assert(uncovered,'Native attribution is obscured');
  await link.click();await page.locator('.cesium-credit-lightbox').waitFor({state:'visible'});
  await page.locator('.cesium-credit-lightbox-close').click();
  await page.locator('.cesium-credit-lightbox-overlay').waitFor({state:'hidden'});
}
async function checkNoOperatorControls(page){
  assert.equal(await page.getByRole('button',{name:/^Settings$|Configure access|Configure Earth imagery|Start analysis|Generate briefing/i}).count(),0,'Operator action rendered in public workspace');
  assert.equal(await page.locator('input[type="password"],.header-costs,.workspace-subnav').count(),0,'Private controls rendered in public workspace');
  assert.equal(await page.getByLabel(/API key|operator key|admin key|browser key/i).count(),0,'Credential editor rendered in public workspace');
}
function attachNetworkProof(page,row,allowedApi){
  row.network={config_requests:0,status_requests:0,forbidden_api_requests:0,media_requests:0,
    publication_observation_requests:0,publication_aircraft_requests:0,
    application_nonread_requests:0,websockets:0,google_roots_ok:0,google_tiles_ok:0};
  page.on('request',request=>{
    const url=new URL(request.url());
    if(url.origin!==base.origin)return;
    if(!['GET','HEAD'].includes(request.method()))row.network.application_nonread_requests++;
    if(url.pathname==='/api/config')row.network.config_requests++;
    if(url.pathname==='/api/status')row.network.status_requests++;
    if(url.pathname==='/api/publication/observations')row.network.publication_observation_requests++;
    if(url.pathname==='/api/publication/aircraft')row.network.publication_aircraft_requests++;
    if(url.pathname.startsWith('/api/')&&(!allowedApi.has(url.pathname)||url.search))row.network.forbidden_api_requests++;
    if(url.pathname.startsWith('/videos/'))row.network.media_requests++;
  });
  page.on('websocket',()=>row.network.websockets++);
  page.on('response',response=>{
    const url=new URL(response.url());
    if(url.hostname!=='tile.googleapis.com'||!url.pathname.startsWith('/v1/3dtiles/')||!response.ok())return;
    if(url.pathname==='/v1/3dtiles/root.json')row.network.google_roots_ok++;
    else row.network.google_tiles_ok++;
  });
}
async function run(){
  fs.mkdirSync(output,{recursive:true});
  for(const name of engines){
    let browser;
    try{browser=await({chromium,firefox,webkit}[name]).launch({headless:true,args:name==='chromium'?['--enable-unsafe-swiftshader']:[]});}
    catch(error){receipt.cases.push({browser:name,status:'runtime_unavailable',error:sanitize(error.message)});save();continue;}
    for(const viewport of viewports){
      const row={browser:name,version:browser.version(),viewport,status:'running',checks:[],page_errors:[]};
      receipt.cases.push(row);save();const start=Date.now();
      const context=await browser.newContext({viewport,hasTouch:viewport.width<768,deviceScaleFactor:1});
      const page=await context.newPage();page.setDefaultTimeout(15000);
      page.on('pageerror',error=>row.page_errors.push(sanitize(error.message)));
      try{
        const response=await context.request.get(new URL('/api/config',base).href);
        assert(response.ok(),'Public configuration unavailable');
        const config=await response.json();
        assert(config.public_read_only===true&&config.public_reports_enabled===false&&config.public_tracking_enabled===false
          &&config.public_media_enabled===false,'Private public-profile capabilities must stay disabled');
        if(requirePublicData)assert(config.public_observations_enabled===true&&config.public_aircraft_enabled===true,'Both dedicated public source capabilities are required');
        assert(config.google_earth_enabled===true&&!!config.google_maps_browser_key,'Google imagery must be configured for this qualification');
        attachNetworkProof(page,row,allowedApiPaths(config));
        row.publications={};
        for(const [kind,enabled] of [['observations',config.public_observations_enabled],['aircraft',config.public_aircraft_enabled]]){
          if(enabled!==true)continue;
          const read=await context.request.get(new URL(`/api/publication/${kind}`,base).href);
          assert(read.ok(),`Public ${kind} API unavailable`);
          row.publications[kind]=inspectPublication(await read.json(),kind,requirePublicData);
        }
        row.checks.push(requirePublicData?'actual_nonempty_NASA_and_ADSB_public_capabilities':'actual_public_capabilities_closed_without_published_data');
        await page.addInitScript(()=>localStorage.setItem('cm_seen_methods_v2','1'));
        await page.goto(new URL('/?view=earth',base).href,{waitUntil:'domcontentloaded',timeout:30000});
        await page.locator('header h1').first().waitFor();
        await page.getByText(config.public_observations_enabled===true?'NASA thermal context and selected aircraft observations · no verified strike, mission or complete conflict coverage claim.':'Historical reports are withheld pending publication approval. No live coverage is claimed.',{exact:true}).waitFor();
        const canvas=page.locator('.cesium-widget canvas');await canvas.waitFor({state:'visible',timeout:30000});
        const handle=await canvas.elementHandle();
        await page.waitForFunction(()=>document.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')==='ready',null,{timeout:45000});
        await page.waitForFunction(()=>document.querySelector('.cesium-widget-credits')?.textContent?.includes('Google'),null,{timeout:15000});
        await settleLayout(page);row.earth_layout=await checkLayout(page,'Earth');
        await checkAttribution(page);await checkNoOperatorControls(page);
        row.checks.push('real_google_ready_native_attribution_visible_clickable');
        const feed=page.getByRole('button',{name:/^Feed.*open report feed/i});
        const mobileFeed=await visible(feed);
        if(mobileFeed){
          await feed.click();await page.getByRole('dialog',{name:'Report feed'}).waitFor();
        }
        if(requirePublicData){
          const panel=page.getByRole('region',{name:'Public thermal observations',exact:true});
          await panel.getByRole('heading',{name:'Reported ADS-B positions',exact:true}).waitFor();
          await panel.getByRole('heading',{name:'Thermal observations available',exact:true}).waitFor();
          assert.match(await panel.textContent(),/[1-9][0-9]* positions in the latest published snapshot/,'Nonempty aircraft panel not rendered');
          assert.match(await panel.textContent(),/[1-9][0-9]* of [1-9][0-9]* eligible pixels/,'Nonempty NASA panel not rendered');
          for(const [label,target] of [['NASA citation','https://www.earthdata.nasa.gov/data/projects/lance#ed-firms-citation'],['Source disclaimer','https://nrt4.modaps.eosdis.nasa.gov/api/v2/content/archives/FIRMS/README.pdf']])assert.equal(await panel.getByRole('link',{name:label,exact:true}).getAttribute('href'),target);
          const nasaLink=panel.getByRole('link',{name:'Download this NASA dataset',exact:true});
          await nasaLink.scrollIntoViewIfNeeded();assert(await nasaLink.isVisible(),'NASA exact download inaccessible');
          row.downloads={};
          const nasaHref=await nasaLink.getAttribute('href');
          assert.match(nasaHref,/^\/api\/publication\/observations\/download\/[a-f0-9]{64}$/,'NASA link is not exact-batch');
          row.downloads.observations=await checkDownload(context,nasaHref,'observations');
          row.checks.push('public_panel_actual_thermal_aircraft_counts_citation_exact_NASA_download');
        }else await page.getByRole('heading',{name:'Reports withheld',exact:true}).waitFor();
        await settleLayout(page);await checkLayout(page,'Public data panel');
        if(mobileFeed)await page.getByRole('button',{name:'Close report feed',exact:true}).click();
        if(requirePublicData){
          const attribution=page.locator('.public-data-attribution');await attribution.waitFor({state:'visible'});
          assert.equal(await attribution.getByRole('link',{name:'adsb.lol',exact:true}).getAttribute('href'),'https://www.adsb.lol/docs/open-data/api');
          assert.equal(await attribution.getByRole('link',{name:'ODbL 1.0',exact:true}).getAttribute('href'),'https://opendatacommons.org/licenses/odbl/1-0/');
          const link=attribution.getByRole('link',{name:'Download ADS-B dataset',exact:true});assert(await link.isVisible(),'Aircraft derivative download inaccessible');
          const href=await link.getAttribute('href');assert.match(href,/^\/api\/publication\/aircraft\/download\/[a-f0-9]{64}$/,'Aircraft link is not exact-batch');
          row.downloads.aircraft=await checkDownload(context,href,'aircraft');
          await page.waitForFunction(()=>Number(document.querySelector('.earth-coverage')?.getAttribute('data-position-count'))>0,null,{timeout:20000});
          row.rendered_positions=Number(await page.locator('.earth-coverage').getAttribute('data-position-count'));
          const controls=page.getByRole('button',{name:'Controls — show Earth navigation',exact:true});
          const openedControls=await visible(controls);
          if(openedControls)await controls.click();
          await page.getByRole('button',{name:/^Layers /}).click();
          const layers=page.getByRole('region',{name:'Spatial layers',exact:true});
          row.earth_source_counts={};
          for(const [kind,label] of [['aircraft','ADS-B positions'],['observations','Thermal observations']]){
            const checkbox=layers.getByRole('checkbox',{name:new RegExp(`^${label} `)});
            assert(await checkbox.isChecked(),`${label} layer is not enabled`);
            const count=Number(await checkbox.locator('..').locator('b').textContent());
            assert(count>0,`${label} has no accepted Earth markers`);
            row.earth_source_counts[kind]=count;
          }
          await page.getByRole('button',{name:'Close spatial layers',exact:true}).click();
          if(openedControls)await page.getByRole('button',{name:'Hide controls — Earth navigation',exact:true}).click();
          row.checks.push('visible_ODbL_attribution_exact_aircraft_download_both_enabled_nonempty_Earth_layers');
        }else row.checks.push('withheld_reports_explained_without_empty_live_claim');
        for(const tab of ['Media','Brief','Earth','Media','Earth']){
          await selectTab(page,tab);
          if(tab!=='Earth')await page.getByRole('heading',{name:tab==='Media'?'Media is not published':'Briefings are not published',exact:true}).waitFor();
          assert(await page.evaluate(node=>node===document.querySelector('.cesium-widget canvas'),handle),'Earth canvas remounted on tab transition');
          await checkNoOperatorControls(page);await checkLayout(page,tab);
        }
        row.checks.push('all_tabs_explicit_publication_states_same_earth_canvas_no_operator_controls');
        await page.getByRole('button',{name:'Sources & health',exact:true}).click();
        await page.getByRole('heading',{name:'Public research scope',exact:true}).waitFor();
        assert(await page.getByText('Withheld pending publication approval',{exact:true}).count()>=2,'Source health must identify both withheld surfaces');
        await settleLayout(page);await checkLayout(page,'Sources and health');
        await page.getByRole('button',{name:'Close source health',exact:true}).click();
        row.checks.push('public_source_health_scope_and_mobile_dialog');
        await page.waitForTimeout(settleMs);await settleLayout(page);
        await checkLayout(page,'Settled Earth');await checkNoOperatorControls(page);
        assert(await page.evaluate(node=>node===document.querySelector('.cesium-widget canvas'),handle),'Earth canvas remounted during observation');
        assert.equal(await page.locator('.earth-workspace').getAttribute('data-earth-provider'),'ready','Google imagery ceased to be ready');
        assert(row.network.google_roots_ok>0&&row.network.google_tiles_ok>0,'No actual successful Google root and content requests were observed');
        assert(row.network.status_requests>=2,'The status polling cycle was not observed');
        if(requirePublicData){
          assert(row.network.publication_observation_requests>=1&&row.network.publication_aircraft_requests>=3,'Dedicated publication polling cycles were not observed');
          for(const kind of ['observations','aircraft']){
            const read=await context.request.get(new URL(`/api/publication/${kind}`,base).href);assert(read.ok());
            row.publications_after_settle??={};row.publications_after_settle[kind]=inspectPublication(await read.json(),kind,true);
          }
        }
        for(const counter of ['forbidden_api_requests','media_requests','application_nonread_requests','websockets'])assert.equal(row.network[counter],0,`Unexpected public background activity: ${counter}`);
        assert.equal(row.page_errors.length,0,'Uncaught browser runtime error');
        row.checks.push('35_second_settle_no_hidden_data_media_operator_polls_or_websockets_no_page_errors');
        row.status='passed';
      }catch(error){row.status='failed';row.error=sanitize(error.message);}
      finally{row.seconds=(Date.now()-start)/1000;await context.close();save();console.log(JSON.stringify({browser:name,viewport,status:row.status,seconds:row.seconds,error:row.error}));}
    }
    await browser.close();
  }
  receipt.ended_at=new Date().toISOString();receipt.passed=receipt.cases.filter(row=>row.status==='passed').length;
  receipt.failed=receipt.cases.filter(row=>row.status!=='passed').length;receipt.status=receipt.failed?'findings_or_unavailable':'passed';save();
  process.exitCode=receipt.failed?1:0;
}
async function checkDownload(context,href,kind){
  const response=await context.request.get(new URL(href,base).href);
  assert(response.ok(),`Exact ${kind} download unavailable`);
  assert.match(response.headers()['content-disposition']||'',/^attachment;/,'Dataset is not downloadable');
  const payload=await response.json(),id=href.split('/').at(-1);
  assert.equal(payload.batch_id,id,'Download silently substituted another snapshot');
  assert(payload.status==='ok'&&payload.payload?.source===(kind==='observations'?'nasa_firms_noaa20':'adsb_lol'),'Download source/payload missing');
  const count=(kind==='observations'?payload.payload.observations:payload.payload.aircraft)?.length;
  assert(Number.isInteger(count)&&count>0,'Exact derivative download is empty');
  if(kind==='aircraft')assert(payload.license==='ODbL-1.0'&&payload.payload.license==='ODbL-1.0'&&payload.attribution.includes('adsb.lol'),'Derivative license notice missing');
  return {status:response.status(),batch_id:id,records:count};
}
module.exports={inspectPublication,allowedApiPaths};
if(require.main===module)run().catch(error=>{receipt.status='observer_failed';receipt.error=sanitize(error.message);save();process.exitCode=1;});
