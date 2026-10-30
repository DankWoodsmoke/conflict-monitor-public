/* Real browser engines with explicitly bounded emulation. No screenshots, traces,
 * browser storage, publisher text, provider URLs or configuration values are saved. */
const {chromium, firefox, webkit} = require('../frontend/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = process.env.CM_BASE_URL || 'http://127.0.0.1:5190';
const output = process.env.CM_REFLOW_OUTPUT || 'artifacts/mobile-reflow';
if (fs.existsSync(output)) throw new Error('Preserve earlier evidence; choose a fresh CM_REFLOW_OUTPUT');
fs.mkdirSync(output, {recursive:true});
const receipt = {started_at:new Date().toISOString(), cases:[], page_errors:[], api_posts:0,
  target_spacing_reference:'https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum/',limitations:[
  'Desktop Chromium, Firefox and WebKit are not physical iOS or Android devices.',
  'Viewport reflow, controlled text enlargement and a Firefox minimum-font preference are distinct tests; none is native iOS Dynamic Type.',
  'This probe does not certify screen-reader speech, all contrast, browser chrome, memory-pressure eviction or every application state.',
  'Google imagery must be configured and ready; unavailable prerequisites fail instead of being skipped.'
]};
const save = () => fs.writeFileSync(path.join(output,'receipt.json'), JSON.stringify(receipt,null,2));
const safe = value => String(value).replace(/https?:\/\/[^\s"<>]+/g,'[URL omitted]').slice(0,400);
async function ready(page) {
  await page.locator('.earth-workspace[data-earth-provider="ready"]').waitFor({timeout:60000});
}
function observe(page, engine) {
  page.on('pageerror', error => receipt.page_errors.push({engine, error:safe(error.message)}));
  page.on('request', request => {
    if (request.method()==='POST' && new URL(request.url()).pathname.startsWith('/api/')) receipt.api_posts++;
  });
}
async function shell(page) {
  return page.evaluate(() => {
    const targets=[...document.querySelectorAll('button,a[href],summary,input,select,[role="button"]')]
      .filter(n=>n.getClientRects().length&&!n.closest('[inert],[hidden]')&&!n.hasAttribute('disabled'));
    // SC2.5.8: the24px circle must miss every other target, including the
    // corresponding24px circle of another undersized target.
    const spacing=(node,box)=>{
      const x=box.left+box.width/2,y=box.top+box.height/2;
      return x>=12&&y>=12&&x<=innerWidth-12&&y<=innerHeight-12&&targets.every(other=>{
        if(other===node||node.contains(other)||other.contains(node))return true;
        const r=(other.closest('label')||other).getBoundingClientRect();
        if(r.width<24||r.height<24){
          const dx=x-(r.left+r.width/2),dy=y-(r.top+r.height/2);
          return dx*dx+dy*dy>=576;
        }
        const dx=x-Math.max(r.left,Math.min(x,r.right)),dy=y-Math.max(r.top,Math.min(y,r.bottom));
        return dx*dx+dy*dy>=144;
      });
    };
    return {
    viewport:{width:innerWidth, height:innerHeight, dpr:devicePixelRatio,
      visual_width:visualViewport?.width, visual_height:visualViewport?.height, visual_scale:visualViewport?.scale},
    document_width:document.documentElement.scrollWidth,
    controls:[...document.querySelectorAll('.app-header button,.mobile-bottom-nav button')]
      .filter(node => node.getClientRects().length>0).map(node => {
        const box=node.getBoundingClientRect(), range=document.createRange(); range.selectNodeContents(node);
        const left=Math.max(0,box.left),right=Math.min(innerWidth,box.right);
        const top=Math.max(0,box.top),bottom=Math.min(innerHeight,box.bottom);
        const hit=document.elementFromPoint((left+right)/2,(top+bottom)/2);
        return {name:node.getAttribute('aria-label')||node.textContent.trim().slice(0,80),
          left:box.left,right:box.right,top:box.top,bottom:box.bottom,
          visible_hit_width:right-left,visible_hit_height:bottom-top,visible_center_hit:hit===node||node.contains(hit),
          undersized_target_spacing_exception:box.width<24||box.height<24?spacing(node,box):null,
          text_rects:[...range.getClientRects()].filter(r=>r.width&&r.height).map(r=>({left:r.left,right:r.right,top:r.top,bottom:r.bottom}))};
      })
    };
  });
}
function checkShell(measurement) {
  const {width,height}=measurement.viewport;
  assert(measurement.document_width<=width+1,'Document overflows its viewport');
  assert(measurement.controls.length>=2,'Header controls unavailable');
  for (const control of measurement.controls) {
    // A clipped decorative padding edge does not erase a target. Require its
    // actual visible hit area and the entire readable caption, not scrollWidth.
    const fullTarget=control.visible_hit_width>=24&&control.visible_hit_height>=24;
    const spacedSmallTarget=control.undersized_target_spacing_exception===true;
    assert((fullTarget||spacedSmallTarget)&&control.visible_center_hit,
      'Header/navigation target lacks a24CSSpx hit area or a measured nonintersecting24px spacing circle');
    assert(control.text_rects.every(r=>r.left>=-1 && r.right<=width+1),'Header/navigation text is clipped horizontally');
  }
}
async function sameCanvas(page, canvas) {
  assert(await page.evaluate(node=>node===document.querySelector('.cesium-widget canvas'),canvas),'Earth canvas remounted');
}
async function enlargeText(page) {
  return page.evaluate(() => {
    const rows=[];
    for (const node of document.querySelectorAll('body *')) {
      if(node.closest('svg,canvas,[hidden],[inert]')) continue;
      const own=[...node.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim();
      if(!/[\p{L}\p{N}]/u.test(own)) continue;
      const style=getComputedStyle(node);
      if(style.display==='none'||style.visibility==='hidden') continue;
      const size=parseFloat(style.fontSize), line=parseFloat(style.lineHeight);
      if(Number.isFinite(size)) rows.push({node,size,line:Number.isFinite(line)?line:size*1.2});
    }
    for(const {node,size,line} of rows) {
      node.style.setProperty('font-size',size*2+'px','important');
      node.style.setProperty('line-height',Math.max(line*2,size*3)+'px','important');
    }
    return {affected_elements:rows.length, method:'Controlled200% computed-font override and1.5line-height; pure pictographic glyphs excluded. Not native Safari DynamicType.'};
  });
}
async function reachable(page, selector) {
  const rows=[];
  for (const target of await page.locator(selector).all()) {
    await target.scrollIntoViewIfNeeded();
    const row=await target.evaluate(node=>{
      const box=node.getBoundingClientRect(), hit=document.elementFromPoint(box.left+box.width/2,box.top+box.height/2);
      return {name:node.getAttribute('aria-label')||node.textContent.trim().slice(0,70),
        fully_in_view:box.left>=0&&box.right<=innerWidth&&box.top>=0&&box.bottom<=innerHeight,
        center_hit:hit===node||node.contains(hit),width:box.width,height:box.height};
    });
    assert(row.fully_in_view&&row.center_hit,'Dialog control cannot be brought fully into view and hit');
    rows.push(row);
  }
  assert(rows.length>0,'Expected dialog controls unavailable');
  return rows;
}
async function fontDialogs() {
  const row={engine:'firefox',profile:'Actual minimum-font preference24px',viewport:{width:320,height:740},states:[],status:'running'};
  receipt.cases.push(row); let browser;
  try {
    browser=await firefox.launch({headless:true,firefoxUserPrefs:{'font.minimum-size.x-western':24,'font.minimum-size.x-unicode':24}});
    row.version=browser.version(); const page=await browser.newPage({viewport:row.viewport,hasTouch:true}); observe(page,'firefox minimum-font');
    await page.goto(base+'/?view=earth',{waitUntil:'domcontentloaded'}); await ready(page); row.initial_shell=await shell(page);save();checkShell(row.initial_shell);
    await page.getByRole('button',{name:'Methods and evidence limitations',exact:true}).click();
    for (const tab of ['Overview','Evidence & sources','Deployment']) {
      await page.getByRole('button',{name:tab,exact:true}).click();
      const targets=await reachable(page,'.methods-dialog header button,.methods-dialog nav button,.methods-dialog footer button');
      await page.locator('.methods-dialog').evaluate(node=>node.scrollTop=0);
      await page.locator('.methods-body').focus();
      const before=await page.locator('.methods-dialog').evaluate(node=>node.scrollTop);
      await page.keyboard.press('PageDown'); await page.waitForTimeout(250);
      const after=await page.locator('.methods-dialog').evaluate(node=>node.scrollTop);
      assert(after>before,'Methods body cannot be scrolled with a real PageDown key');
      row.states.push({name:'Methods '+tab,targets,native_keyboard_scroll:{before,after}}); save();
    }
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'Settings',exact:true}).click();
    row.states.push({name:'Settings',targets:await reachable(page,'.settings-dialog header button,.settings-dialog footer button')});
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'Controls — show Earth navigation',exact:true}).click();
    await page.getByRole('button',{name:/^Layers/}).click();
    row.states.push({name:'Layers',targets:await reachable(page,'.earth-panel-heading button')});
    await page.keyboard.press('Escape');
    await page.locator('.mobile-bottom-nav').getByRole('button',{name:/Media/}).click();
    await page.getByRole('button',{name:'Narrated briefing',exact:true}).click();
    await page.getByRole('button',{name:'Hide captions',exact:true}).waitFor({state:'visible',timeout:20000});
    const captionTargets=await reachable(page,'.local-briefing-panel button[aria-pressed]');
    await page.getByText('Narration transcript',{exact:true}).click();
    const transcript=page.getByRole('region',{name:'Complete narration transcript',exact:true});
    await transcript.focus();const captionBefore=await transcript.evaluate(node=>({top:node.scrollTop,height:node.clientHeight,scroll_height:node.scrollHeight}));
    await page.keyboard.press('PageDown');await page.waitForTimeout(250);
    const captionAfter=await transcript.evaluate(node=>node.scrollTop);
    assert(captionBefore.scroll_height<=captionBefore.height||captionAfter>captionBefore.top,'Enlarged narration transcript cannot be scrolled by keyboard');
    row.states.push({name:'Minimum-font caption controls and narration transcript',targets:captionTargets,
      native_keyboard_scroll:{...captionBefore,after:captionAfter}});
    row.status='PASS';
  } catch(error) {row.status='FAIL';row.error=safe(error.message);}
  finally {if(browser)await browser.close();save();console.log(JSON.stringify({engine:row.engine,profile:row.profile,status:row.status,states:row.states.length,error:row.error}));}
}
(async()=>{
  for(const [engine,type] of Object.entries({chromium,firefox,webkit})) {
    const row={engine,profile:'Emulated viewport/touch and controlled text enlargement',states:[],status:'running'};
    receipt.cases.push(row); let browser;
    try {
      browser=await type.launch({headless:true,args:engine==='chromium'?['--enable-unsafe-swiftshader']:[]});row.version=browser.version();
      const context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,deviceScaleFactor:2});
      const page=await context.newPage();observe(page,engine);await page.goto(base+'/?view=earth',{waitUntil:'domcontentloaded'});await ready(page);
      const canvas=await page.locator('.cesium-widget canvas').elementHandle();
      const initial=await shell(page);checkShell(initial);row.states.push({name:'portrait baseline',...initial});
      for(const viewport of [{width:390,height:620},{width:390,height:780},{width:844,height:390},{width:390,height:844},{width:640,height:500},{width:320,height:740}]) {
        await page.setViewportSize(viewport);await page.waitForTimeout(250);await sameCanvas(page,canvas);
        const measurement=await shell(page);checkShell(measurement);row.states.push({name:'viewport resize/reflow equivalent',same_canvas:true,...measurement});
      }
      await page.setViewportSize({width:390,height:844});row.text_enlargement=await enlargeText(page);await page.waitForTimeout(250);
      const enlarged=await shell(page);checkShell(enlarged);await sameCanvas(page,canvas);
      row.states.push({name:'controlled200% text enlargement',same_canvas:true,...enlarged});row.status='PASS';
    } catch(error) {row.status='FAIL';row.error=safe(error.message);}
    finally {if(browser)await browser.close();save();console.log(JSON.stringify({engine,status:row.status,states:row.states.length,error:row.error}));}
  }
  await fontDialogs();
  receipt.status=receipt.cases.every(row=>row.status==='PASS')&&receipt.api_posts===0&&receipt.page_errors.length===0?'PASS':'FAIL';
  receipt.ended_at=new Date().toISOString();save();if(receipt.status!=='PASS')process.exitCode=1;
})().catch(error=>{receipt.status='OBSERVER_FAILED';receipt.error=safe(error.message);receipt.ended_at=new Date().toISOString();save();process.exitCode=1;});
