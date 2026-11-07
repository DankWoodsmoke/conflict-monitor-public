// Read the composed screenshot, not a cleared WebGL drawing buffer. No images,
// provider URLs or browser storage are retained by this helper.
const assert=require('node:assert/strict');

function inspectRasterSamples(colors){
  assert(Array.isArray(colors)&&colors.every(row=>Array.isArray(row)&&row.length===3&&row.every(v=>Number.isInteger(v)&&v>=0&&v<=255)),'Invalid screenshot samples');
  const bins=new Set();let sum=0,squares=0,bright=0;
  for(const [r,g,b] of colors){sum+=r+g+b;squares+=r*r+g*g+b*b;bright+=Math.max(r,g,b)>40?1:0;bins.add((r>>4)*256+(g>>4)*16+(b>>4));}
  const mean=colors.length?sum/(colors.length*3):0;
  return {samples:colors.length,mean,stddev:colors.length?Math.sqrt(Math.max(0,squares/(colors.length*3)-mean*mean)):0,
    bright_fraction:colors.length?bright/colors.length:0,color_bins:bins.size};
}

function assertVisibleEarthRaster(metrics){
  // These bounds reject the known flat dark/transparent canvas failure in the
  // fixed regional Earth view. They are not an image-quality or ground-truth test.
  assert(metrics.samples>=16,'Too little unobscured Earth to qualify its composed raster');
  assert(metrics.bright_fraction>=0.25&&metrics.stddev>=10&&metrics.color_bins>=16,
    'Composed Earth raster is blank, flat, or insufficiently textured');
}

async function measureVisibleEarthRaster(page){
  const points=await page.evaluate(()=>{
    const canvas=document.querySelector('.cesium-widget canvas');
    if(!canvas)return [];
    const rect=canvas.getBoundingClientRect(),points=[];
    for(let y=1;y<24;y++)for(let x=1;x<32;x++){
      const px=Math.floor(rect.left+rect.width*x/32),py=Math.floor(rect.top+rect.height*y/24);
      if(px>=0&&py>=0&&px<innerWidth&&py<innerHeight&&document.elementFromPoint(px,py)===canvas)points.push([px,py]);
    }
    return points;
  });
  const png=await page.screenshot({type:'png',fullPage:false,scale:'css',timeout:15000});
  const colors=await page.evaluate(async({base64,points})=>{
    const image=new Image();image.src='data:image/png;base64,'+base64;await image.decode();
    const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
    const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);
    const earth=document.querySelector('.cesium-widget canvas');
    return points.filter(([x,y])=>document.elementFromPoint(x,y)===earth&&x<image.width&&y<image.height)
      .map(([x,y])=>Array.from(ctx.getImageData(x,y,1,1).data).slice(0,3));
  },{base64:png.toString('base64'),points});
  const metrics=inspectRasterSamples(colors);assertVisibleEarthRaster(metrics);return metrics;
}

module.exports={inspectRasterSamples,assertVisibleEarthRaster,measureVisibleEarthRaster};
