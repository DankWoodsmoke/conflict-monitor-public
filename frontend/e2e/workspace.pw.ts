import {test,expect} from "@playwright/test";

const live=process.env.CM_LIVE==="1";
const google=process.env.CM_EXPECT_GOOGLE==="1";
const entry=live?"/?view=earth":"/?showcase=true&view=earth";

async function openWorkspace(page:import("@playwright/test").Page){
 await page.goto(entry);
 await page.locator("header h1").waitFor();
 if(process.env.CM_GOOGLE_KEY){
  // Optional operator key travels only in process and React memory. No trace,
  // HAR, screenshots, browser storage or key-bearing URL is recorded here.
  await page.evaluate(key=>window.dispatchEvent(new CustomEvent("cm-earth-provider",{detail:{key,enabled:true}})),process.env.CM_GOOGLE_KEY);
 }
}

test.beforeEach(async({page})=>{
 await page.addInitScript(()=>localStorage.setItem("cm_seen_methods_v2","1"));
 if(process.env.CM_DEBUG_RAF==="1")await page.addInitScript(()=>{
  const original=window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame=callback=>{const scheduled=new Error("Animation scheduled").stack;return original(time=>{try{callback(time);}catch(error){if(error instanceof Error)error.stack+=`\n${scheduled}`;throw error;}});};
 });
});

test("reports, persistent Earth and both workspace panels remain usable",async({page,request})=>{
 const errors:string[]=[];page.on("pageerror",error=>errors.push((error.stack||error.message).replace(/([?&]key=)[^\s&]+/g,"$1[redacted]")));
 await openWorkspace(page);
 const intro=page.getByRole("button",{name:/close.*(?:about|methods)|begin monitoring/i});
 if(await intro.count())await intro.first().click();
 await expect(page.getByRole("navigation",{name:"Workspace views"})).toBeVisible();
 await expect(page.getByRole("navigation",{name:"Workspace views"}).getByRole("button")).toHaveCount(3);
 const axisLabels=await page.locator('[data-axis-day]').evaluateAll(nodes=>nodes.map(node=>{const rect=node.getBoundingClientRect();return {left:rect.left,right:rect.right};}));
 expect(axisLabels.length).toBeGreaterThan(0);expect(axisLabels.length).toBeLessThanOrEqual(24);
 for(let i=1;i<axisLabels.length;i++)expect(axisLabels[i].left-axisLabels[i-1].right).toBeGreaterThan(8);
 if(live){
  const response=await request.get("/api/events?limit=50");expect(response.ok()).toBeTruthy();
  const reports=await response.json();expect(Array.isArray(reports)).toBeTruthy();expect(reports.length).toBeGreaterThan(0);
  expect(reports.some((event:any)=>event.source==="demo"||event.synthetic)).toBeFalsy();
  await expect(page.getByText(reports[0].summary,{exact:true}).first()).toBeVisible();
  await expect(page.locator(".showcase-banner")).toHaveCount(0);
  if(reports.some((event:any)=>event.severity===0))await expect(page.getByText("UNSCORED",{exact:true}).first()).toBeVisible();
 }
 await page.getByRole("navigation",{name:"Workspace views"}).getByRole("button",{name:/^Earth —/}).click();
 await expect(page.locator(".cesium-widget canvas")).toBeVisible();
 const canvas=await page.locator(".cesium-widget canvas").elementHandle();
 if(google){await expect(page.locator(".earth-workspace")).toHaveAttribute("data-earth-provider","ready");await expect(page.locator(".earth-provider-status")).toContainText("Photographic imagery");await expect(page.locator(".cesium-widget-credits")).toContainText("Google");}
 await page.getByRole("navigation",{name:"Workspace views"}).getByRole("button",{name:/^Media —/}).click();
 await expect(page.getByRole("complementary",{name:"Media workspace panel"})).toBeVisible();
 expect(await page.evaluate(node=>node===document.querySelector(".cesium-widget canvas"),canvas)).toBeTruthy();
 await expect(page.getByText(/(?:SOURCE BRIEFING|SITUATION BRIEF|SYNTHETIC BRIEFING)/).first()).toBeVisible();
 await page.getByRole("navigation",{name:"Workspace views"}).getByRole("button",{name:/^Situation brief —/}).click();
 await expect(page.getByRole("complementary",{name:"Brief workspace panel"})).toBeVisible();
 expect(await page.evaluate(node=>node===document.querySelector(".cesium-widget canvas"),canvas)).toBeTruthy();
 if(live){await expect(page.getByText(/SOURCE BRIEFING|No source briefing yet/).first()).toBeVisible();expect(await page.locator("body").innerText()).not.toContain("50/100");}
 else await expect(page.getByText("SOURCE REFERENCES",{exact:true}).first()).toBeVisible();
 await page.getByRole("button",{name:"Back to Earth — close workspace panel"}).click();
 await expect(page.locator(".workspace-panel")).toHaveCount(0);
 await expect(page.locator(".leaflet-container")).toHaveCount(0);
 expect(errors).toEqual([]);
});

test("provider health and settings support keyboard dismissal",async({page})=>{
 await openWorkspace(page);
 const dismiss=page.getByRole("button",{name:/close.*(?:about|methods)|begin monitoring/i});if(await dismiss.count())await dismiss.first().click();
 if(live){await page.getByRole("button",{name:"Sources & health",exact:true}).click();await expect(page.getByRole("heading",{name:"Sources & health"})).toBeVisible();await expect(page.getByText("Newest source time age").first()).toBeVisible();await page.keyboard.press("Escape");await expect(page.getByRole("heading",{name:"Sources & health"})).toHaveCount(0);}
 await page.getByRole("button",{name:"Settings",exact:true}).click();await expect(page.getByRole("heading",{name:"Earth & data"})).toBeVisible();
 await page.keyboard.press("Escape");await expect(page.getByRole("heading",{name:"Earth & data"})).toHaveCount(0);
 expect(await page.evaluate(()=>Object.keys(sessionStorage).some(key=>/google|token|key/i.test(key)))).toBeFalsy();
});

test("portrait and landscape navigation and dialogs fit emulated viewports",async({page})=>{
 await page.setViewportSize({width:390,height:844});await openWorkspace(page);
 const dismiss=page.getByRole("button",{name:/close.*(?:about|methods)|begin monitoring/i});if(await dismiss.count())await dismiss.first().click();
 const nav=page.locator(".mobile-bottom-nav");await expect(nav).toBeVisible();
 for(const size of [{width:390,height:844},{width:844,height:390}]){
  await page.setViewportSize(size);
  for(const name of ["Earth","Media","Brief"]){await nav.getByRole("button",{name:new RegExp(name)}).click();await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();if(name!=="Earth")await expect(page.locator(".workspace-panel")).toBeVisible();}
 }
 await nav.getByRole("button",{name:/Earth/}).click();
 await page.getByRole("button",{name:"Settings",exact:true}).click();await expect(page.getByRole("dialog")).toBeVisible();await page.keyboard.press("Escape");
});

test("old Map and 3D links open the single Earth workspace",async({page})=>{
 for(const alias of ["map","3d"]){
  await page.goto(`/?${live?"":"showcase=true&"}view=${alias}`);
  await expect(page.locator(".earth-workspace")).toBeVisible();
  await expect(page.locator(".leaflet-container")).toHaveCount(0);
  await expect(page.getByRole("navigation",{name:"Workspace views"}).getByRole("button",{name:/^Earth —/})).toHaveAttribute("aria-pressed","true");
 }
});

test("320px showcase keeps Methods text and its complete button reachable",async({page})=>{
 await page.setViewportSize({width:320,height:844});
 await page.goto("/?showcase=true&view=earth");
 await expect(page.locator(".showcase-banner")).toContainText(/Synthetic exercise/i);
 const methods=page.locator(".app-header button").filter({hasText:/^Methods$/});
 await expect(methods).toBeVisible();
 const bounds=await methods.evaluate(node=>{
  const button=node.getBoundingClientRect(),range=document.createRange();range.selectNodeContents(node);
  return {button:{left:button.left,right:button.right},text:[...range.getClientRects()].map(rect=>({left:rect.left,right:rect.right,width:rect.width,height:rect.height}))};
 });
 expect(bounds.button.left).toBeGreaterThanOrEqual(0);expect(bounds.button.right).toBeLessThanOrEqual(320);
 expect(bounds.text.some(rect=>rect.width>0&&rect.height>0)).toBeTruthy();
 for(const rect of bounds.text.filter(rect=>rect.width>0&&rect.height>0)){expect(rect.left).toBeGreaterThanOrEqual(0);expect(rect.right).toBeLessThanOrEqual(320);}
 await methods.click();await expect(page.getByRole("dialog",{name:"Evidence in context."})).toBeVisible();
 await page.keyboard.press("Escape");await expect(page.getByRole("dialog")).toHaveCount(0);
});
