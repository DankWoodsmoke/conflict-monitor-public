/* Bounded browser-native touch camera-motion corroboration.
 * No imagery, frames, publisher text, browser storage or provider keys are saved. */
const {chromium}=require('../frontend/node_modules/playwright');
const {PNG}=require('../frontend/node_modules/playwright-core/lib/utilsBundle.js');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const base=process.env.CM_BASE_URL||'http://127.0.0.1:5190';
const output=process.env.CM_CAMERA_OUTPUT;
assert(output&&!fs.existsSync(output),'Fresh CM_CAMERA_OUTPUT required');
fs.mkdirSync(output,{recursive:true});
const out={started_at:new Date().toISOString(),scope:'Independent bounded browser-native touch camera-motion corroboration on production Google Earth; desktop emulation',criteria:{max_attempts:3,min_roi_pixels:20000,rgb_l1_threshold:60,min_changed_fraction:.35,max_inventory_churn_fraction:.05,min_visible_drop_fraction:.75,min_restored_visible_fraction:.75,restore_must_improve_initial_roi_similarity:true},attempts:[],page_errors:[],api_posts:0,limitations:['No physical device, exact camera-center measurement or same-track-identity proof.','Image buffers remain in memory only; hashes/counts are persisted. Natural collector arrivals and TTL expiry are not frozen.']};
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
out.harness_sha256=hash(fs.readFileSync(__filename));
const save=()=>fs.writeFileSync(path.join(output,'receipt.json'),JSON.stringify(out,null,2));
const safe=e=>String(e.message||e).replace(/https?:\/\/[^\s"<>]+/g,'[URL omitted]').slice(0,350);
function compare(a,b){assert(a.width===b.width&&a.height===b.height);let changed=0,total=0;for(let i=0;i<a.data.length;i+=4){const d=Math.abs(a.data[i]-b.data[i])+Math.abs(a.data[i+1]-b.data[i+1])+Math.abs(a.data[i+2]-b.data[i+2]);total+=d;if(d>out.criteria.rgb_l1_threshold)changed++;}return{pixels:a.width*a.height,changed_pixels:changed,changed_fraction:changed/(a.width*a.height),mean_rgb_l1:total/(a.width*a.height)};}
async function tap(page,locator){const b=await locator.boundingBox();assert(b);await page.touchscreen.tap(b.x+b.width/2,b.y+b.height/2);}
async function nav(page,open){const b=page.locator('.earth-navigation-toggle');if(await b.getAttribute('aria-expanded')!==String(open))await tap(page,b);assert.equal(await b.getAttribute('aria-expanded'),String(open));}
async function count(page){return page.locator('.earth-coverage').evaluate(n=>({enabled:Number(n.dataset.positionCount),visible:Number(n.dataset.visibleCount)}));}
async function same(page,canvas){return page.evaluate(n=>n===document.querySelector('.cesium-widget canvas'),canvas);}
async function reset(page){await nav(page,true);await tap(page,page.getByRole('button',{name:'Region',exact:true}));await page.waitForTimeout(1500);await tap(page,page.getByRole('button',{name:'Globe',exact:true}));await page.waitForTimeout(1600);await nav(page,false);await page.waitForTimeout(300);}
async function capture(page,roi){const b=await page.screenshot({clip:roi});return{image:PNG.sync.read(b),sha256:hash(b)};}
(async()=>{let browser;try{
 browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});out.browser_version=browser.version();
 const context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,deviceScaleFactor:1});const page=await context.newPage();
 page.on('pageerror',e=>out.page_errors.push(safe(e)));page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.startsWith('/api/'))out.api_posts++;});
 await page.addInitScript(()=>localStorage.setItem('cm_seen_methods_v2','1'));await page.goto(base+'/?view=earth',{waitUntil:'domcontentloaded'});
 await page.locator('.earth-workspace[data-earth-provider="ready"]').waitFor({timeout:60000});assert((await page.locator('.cesium-widget-credits').innerText()).includes('Google'));
 const canvas=await page.locator('.cesium-widget canvas').elementHandle();const box=await page.locator('.cesium-widget canvas').boundingBox();assert(box);
 const roi={x:Math.ceil(box.x+box.width*.2),y:Math.ceil(box.y+box.height*.42),width:Math.floor(box.width*.6),height:Math.floor(box.height*.33)};assert(roi.width*roi.height>=20000);out.roi=roi;
 const cdp=await context.newCDPSession(page);
 for(let attempt=1;attempt<=out.criteria.max_attempts;attempt++){
  await reset(page);
  const overlaps=await page.evaluate(roi=>[...document.querySelectorAll('.earth-controls,.earth-navigation,.earth-bottom-stack,.earth-attribution,.cesium-widget-credits,.mobile-bottom-nav,.earth-selection,.earth-layer-panel')].filter(n=>{if(!n.checkVisibility())return false;const b=n.getBoundingClientRect();return b.left<roi.x+roi.width&&b.right>roi.x&&b.top<roi.y+roi.height&&b.bottom>roi.y;}).map(n=>n.className),roi);assert.deepEqual(overlaps,[],'ROI intersects an app control or native attribution');
  const before=await count(page);const first=await capture(page,roi);const started=Date.now();
  await cdp.send('Input.synthesizeScrollGesture',{x:box.x+box.width/2,y:box.y+box.height/2,xDistance:180,yDistance:0,speed:220,gestureSourceType:'touch'});await page.waitForTimeout(700);
  const after=await count(page);const moved=await capture(page,roi);const movement=compare(first.image,moved.image);
  await nav(page,true);await tap(page,page.getByRole('button',{name:'Region',exact:true}));await page.waitForTimeout(1600);const region=await count(page);
  await tap(page,page.getByRole('button',{name:'Globe',exact:true}));await page.waitForTimeout(1600);await nav(page,false);await page.waitForTimeout(300);
  const restored=await count(page);const final=await capture(page,roi);const restoration=compare(first.image,final.image);
  const netLoss=Math.max(0,before.enabled-after.enabled);const churn=Math.abs(after.enabled-before.enabled)/Math.max(1,before.enabled);const maskDrop=before.visible-after.visible;
  const gates={native_command_accepted:true,same_canvas:await same(page,canvas),at_least_four_before_positions:before.visible>=4,inventory_churn_within_five_percent:churn<=.05,visible_mask_drop_beyond_net_inventory_loss:maskDrop-netLoss>=before.visible*.75,central_roi_at_least_35percent_changed:movement.changed_fraction>=.35,region_restores_at_least_75percent_visible:region.visible>=before.visible*.75,globe_reset_restores_at_least_75percent_visible:restored.visible>=before.visible*.75,restoration_improves_initial_scene_similarity:restoration.mean_rgb_l1<movement.mean_rgb_l1};
  out.attempts.push({attempt,before,after,region,restored,elapsed_ms:Date.now()-started,net_inventory_loss:netLoss,inventory_churn_fraction:churn,movement,restoration,initial_roi_sha256:first.sha256,moved_roi_sha256:moved.sha256,restored_roi_sha256:final.sha256,overlay_intersections:overlaps,gates,status:Object.values(gates).every(Boolean)?'PASS':'INCOMPLETE'});save();
  if(Object.values(gates).every(Boolean))break;
 }
 out.status=out.attempts.some(x=>x.status==='PASS')&&!out.page_errors.length&&out.api_posts===0?'PASS':'INCOMPLETE';await context.close();
}catch(e){out.status='INCOMPLETE';out.error=safe(e);}finally{if(browser)await browser.close();out.ended_at=new Date().toISOString();save();console.log(JSON.stringify({status:out.status,attempts:out.attempts.length,page_errors:out.page_errors,api_posts:out.api_posts,error:out.error}));process.exitCode=out.status==='PASS'?0:1;}})();
