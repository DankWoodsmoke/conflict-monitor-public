import {test,expect,chromium,firefox,webkit} from "@playwright/test";
import {createRequire} from "node:module";
const require=createRequire(import.meta.url);
const {inspectRasterSamples,assertVisibleEarthRaster,measureVisibleEarthRaster}=require("../../tools/browser_raster.cjs");

test("raster gate rejects blank, flat and undersampled evidence",()=>{
 for(const samples of [[],Array(100).fill([7,17,26]),Array(100).fill([255,255,255]),Array(100).fill([38,166,230])]){
  expect(()=>assertVisibleEarthRaster(inspectRasterSamples(samples))).toThrow();
 }
 expect(()=>inspectRasterSamples([[NaN,0,0]])).toThrow();
 const texture=Array.from({length:128},(_,i)=>[50+i,100+i%100,30+(i*7)%200]);
 expect(()=>assertVisibleEarthRaster(inspectRasterSamples(texture))).not.toThrow();
});

for(const engine of ["chromium","firefox","webkit"] as const){
 test(`composed WebGL pixels survive buffer resize in ${engine}`,async()=>{
  // Linux Firefox needs an X display for this WebGL check; CI supplies Xvfb.
  // Other engine/platform paths retain their native headless behavior.
  const headless=!(process.platform==="linux"&&engine==="firefox");
  const browser=await({chromium,firefox,webkit}[engine]).launch({headless,channel:undefined,args:[]});
  try{for(let repeat=0;repeat<3;repeat++){
   const context=await browser.newContext({viewport:{width:390,height:664}});
   try{
    await context.route("**/*",route=>route.abort());const page=await context.newPage();
    await page.setContent(`<body style="margin:0;background:white"><canvas id="c"></canvas><script>
      window.webglDiagnostic={created:false,creationErrors:[]};
      const canvas=document.querySelector('canvas');
      canvas.addEventListener('webglcontextcreationerror',event=>window.webglDiagnostic.creationErrors.push(event.statusMessage));
      const gl=canvas.getContext('webgl');window.webglDiagnostic.created=!!gl;
      if(gl){
      function resize(){gl.canvas.width=innerWidth;gl.canvas.height=innerHeight;gl.viewport(0,0,innerWidth,innerHeight)}
      addEventListener('resize',resize);resize();
      function frame(){gl.clearColor(1,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);requestAnimationFrame(frame)}frame();}
    </script>`);
    const diagnostic=await page.evaluate(()=>Reflect.get(window,"webglDiagnostic"));
    expect(diagnostic,`${engine} repeat ${repeat}: WebGL context creation`).toEqual({created:true,creationErrors:[]});
    for(const viewport of [{width:390,height:664},{width:390,height:844},{width:844,height:390}]){
     await page.setViewportSize(viewport);await page.waitForTimeout(300);
     const png=await page.screenshot({scale:"css"});
     const pixel=await page.evaluate(async base64=>{
      const image=new Image();image.src="data:image/png;base64,"+base64;await image.decode();
      const c=document.createElement("canvas");c.width=image.width;c.height=image.height;
      const ctx=c.getContext("2d")!;ctx.drawImage(image,0,0);
      return Array.from(ctx.getImageData(c.width>>1,c.height>>1,1,1).data);
     },png.toString("base64"));
     expect(pixel,`${engine} repeat ${repeat} ${viewport.width}x${viewport.height}: composed WebGL pixel`).toEqual([255,0,0,255]);
    }
    // Visible DOM labels cannot make an absent Earth canvas pass the same gate
    // used by the live matrix. The authored texture then proves the positive path.
    await page.setContent('<body style="margin:0;background:#07111a"><div class="cesium-widget"><canvas width="844" height="390"></canvas></div><div style="position:absolute;inset:0 0 auto;height:120px;background:white">Opaque overlay</div></body>');
    await expect(measureVisibleEarthRaster(page)).rejects.toThrow(/blank|flat|textured/);
    await page.locator("canvas").evaluate((canvas:HTMLCanvasElement)=>{
      const ctx=canvas.getContext("2d")!;
      for(let x=0;x<canvas.width;x+=8)for(let y=0;y<canvas.height;y+=8){ctx.fillStyle=`rgb(${50+x%180},${90+y%140},${30+(x+y)%200})`;ctx.fillRect(x,y,8,8);}
    });
    expect((await measureVisibleEarthRaster(page)).color_bins).toBeGreaterThanOrEqual(16);
   }finally{await context.close();}
  }}finally{await browser.close();}
 });
}
