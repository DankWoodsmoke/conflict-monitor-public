import {test,expect,chromium,firefox,webkit,type Page} from "@playwright/test";
import {readFileSync} from "node:fs";

// Exercise the real styles in an offline layout fixture. The App unit test binds
// this structure to admitted capabilities; the live matrix separately checks Google/data.
const css=["globals.css","earth.css"].map(name=>readFileSync(new URL(`../src/styles/${name}`,import.meta.url),"utf8")).join("\n");
const sizes=[{width:320,height:740},{width:390,height:844},{width:768,height:1024},
 {width:844,height:390},{width:1024,height:768},{width:1100,height:900},{width:1440,height:900}];
function markup(admitted:boolean,publicMode=admitted){return `<style>${css}</style><div id="root">
 <div class="runtime-banner">Offline layout fixture</div>
 <main class="app-grid has-runtime ${publicMode?"public-data-workspace":""}">
  <header class="app-header" style="grid-area:header">Conflict Monitor</header>
  <div class="${admitted?"public-attribution-wrap":"market-strip-wrap"}">${admitted?
   '<div class="public-scope-note public-data-attribution">Thermal: NASA FIRMS · ADS-B: <a href="#provider">adsb.lol</a> · <a href="#license">ODbL 1.0</a> · <a href="#download">Download ADS-B dataset</a> · Partial coverage</div>':'Operator market strip'}</div>
  <div class="earth-stage" style="grid-area:map;min-width:0;min-height:0;overflow:hidden"><div class="earth-workspace">
   <canvas class="earth-canvas"></canvas><div class="earth-bottom-stack"><div class="earth-attribution"><a href="#imagery">Imagery attribution fixture</a></div></div>
  </div></div>
  <div class="sidebar">Published data fixture</div><div class="timeline-wrap" style="grid-area:timeline">${publicMode?'<div class="public-scope-note">NASA thermal context and selected aircraft observations · no verified strike, mission or complete conflict coverage claim.</div>':'Operator timeline fixture'}</div>
 </main><nav class="mobile-bottom-nav"><button>Earth</button><button>Media</button><button>Brief</button></nav></div>`;}

async function checkFooter(page:Page){
 if(await page.locator("main.earth-focused").count()){
  await expect(page.locator(".timeline-wrap")).toBeHidden();return;
 }
 const footer=page.locator(".timeline-wrap"),content=footer.locator(".public-scope-note");
 await expect(footer).toBeVisible();await expect(content).toBeVisible();
 const box=await footer.boundingBox(),text=await content.boundingBox();
 expect(Math.abs(box!.height-text!.height)).toBeLessThanOrEqual(1);
 expect(box!.y+box!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
}

async function checkAttribution(page:Page){
 const attribution=page.locator(".public-data-attribution");await expect(attribution).toBeVisible();
 const geometry=await attribution.evaluate(node=>{
  const box=node.getBoundingClientRect(),header=document.querySelector(".app-header")!.getBoundingClientRect();
  const stage=document.querySelector(".earth-stage")!.getBoundingClientRect();
  return {top:box.top,bottom:box.bottom,headerBottom:header.bottom,stageTop:stage.top,stageHeight:stage.height};
 });
 expect(geometry.top).toBeGreaterThanOrEqual(geometry.headerBottom-1);
 expect(geometry.bottom).toBeLessThanOrEqual(geometry.stageTop+1);
 expect(geometry.stageHeight).toBeGreaterThan(80);
 for(const label of ["adsb.lol","ODbL 1.0","Download ADS-B dataset"]){
  const link=attribution.getByRole("link",{name:label,exact:true});await expect(link).toBeVisible();
  expect(await link.evaluate(node=>{
   const box=node.getBoundingClientRect(),parent=node.parentElement!.getBoundingClientRect();
   const top=document.elementFromPoint(box.left+box.width/2,box.top+box.height/2);
   return box.left>=0&&box.right<=innerWidth&&box.top>=parent.top&&box.bottom<=parent.bottom
    &&box.bottom<=innerHeight&&(top===node||node.contains(top));
  })).toBe(true);
 }
 await attribution.getByRole("link",{name:"Download ADS-B dataset",exact:true}).click();
 await expect(page).toHaveURL(/#download$/);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await checkFooter(page);
}

for(const engine of ["chromium","firefox","webkit"] as const){
 test(`public attribution stays reserved and reachable in ${engine}`,async()=>{
  test.setTimeout(90000);
  // This test launches each bundled engine; do not inherit the suite's Chrome channel.
  const browser=await({chromium,firefox,webkit}[engine]).launch({headless:true,channel:undefined,args:[]});
  try{for(const viewport of sizes){
   const context=await browser.newContext({viewport});
   try{
    const page=await context.newPage();await page.route("**/*",route=>route.abort());
    await page.setContent(markup(true));
    const canvas=await page.locator("canvas").elementHandle();
    for(const tab of ["Earth","Media","Brief","Earth"]){
     await page.evaluate(tab=>{
      const main=document.querySelector("main")!;main.classList.toggle("has-workspace-panel",tab!=="Earth");
      main.querySelector(".workspace-panel")?.remove();
      if(tab!=="Earth"){
       const panel=document.createElement("aside");panel.className="workspace-panel";
       panel.innerHTML=`<div class="workspace-panel-header"><h2>${tab}</h2><button>Back to Earth</button></div><div class="workspace-panel-body">Not published</div>`;main.append(panel);
      }
     },tab);
     await checkAttribution(page);
     expect(await page.evaluate(node=>node===document.querySelector("canvas"),canvas)).toBe(true);
     if(tab!=="Earth"){
      const panel=await page.locator(".workspace-panel").boundingBox(),strip=await page.locator(".public-data-attribution").boundingBox();
      expect(panel!.y).toBeGreaterThanOrEqual(strip!.y+strip!.height-1);
     }else await expect(page.getByRole("link",{name:"Imagery attribution fixture"})).toBeVisible();
    }
    // Extra wrapping changes the content height; panel placement must follow it.
    await page.locator(".public-data-attribution").evaluate(node=>node.prepend("Additional source scope disclosure. ".repeat(4)));
    await checkAttribution(page);
    if(viewport.width>900){
     await page.locator("main").evaluate(node=>node.classList.add("earth-focused"));
     await checkAttribution(page);
    }
    // Withheld/NASA-only public profiles have no aircraft attribution strip,
    // but their explanatory footer must still size to its real wrapped content.
    await page.setContent(markup(false,true));
    await checkFooter(page);
    await page.locator(".timeline-wrap .public-scope-note").evaluate(node=>node.textContent="Historical reports are withheld pending publication approval. No live coverage is claimed.");
    await checkFooter(page);
    await page.setContent(markup(false));
    const mobile=viewport.width<=768||(viewport.width<=900&&viewport.height<=500);
    if(mobile)await expect(page.locator(".market-strip-wrap")).toBeHidden();
    else await expect(page.locator(".market-strip-wrap")).toBeVisible();
   }finally{await context.close();}
  }}finally{await browser.close();}
 });
}
