/* Independent response-to-Cesium projection checks. No rows leave process memory. */
const assert=require('node:assert/strict'),crypto=require('node:crypto');
const specs={observations:{source:'nasa_firms_noaa20',key:'hotspots',limit:2000,cadence:95000},aircraft:{source:'adsb_lol',key:'aircraft',limit:5000,cadence:50000}};
function captureProjection(kind,value,receivedAt){
 const spec=specs[kind];assert(spec,'Unknown public dataset');
 assert.equal(value.source,spec.source);assert(['fresh','empty'].includes(value.status),'Public dataset unavailable');
 assert.match(value.batch_id||'',/^[0-9a-f]{64}$/);const input=value[spec.key];assert(Array.isArray(input)&&input.length<=spec.limit,'Public response exceeds bounds');
 const rows=input.map(row=>{
  assert(Number.isFinite(row.lat)&&Math.abs(row.lat)<=90&&Number.isFinite(row.lon)&&Math.abs(row.lon)<=180,'Invalid public coordinate');
  const stamp=kind==='aircraft'?row.observed_at:row.ts,time=Date.parse(stamp);assert(Number.isFinite(time),'Invalid source clock');
  if(kind==='aircraft')assert.match(row.icao24||'',/^~?[a-f0-9]{6}$/);
  return {id:kind==='aircraft'?`aircraft-${row.icao24}`:`thermal-${row.lat}-${row.lon}-${stamp}`,lat:row.lat,lon:row.lon,time,stale:row.stale===true};
 });
 assert.equal(new Set(rows.map(row=>row.id)).size,rows.length,'Duplicate render identity');
 return {batch_id:value.batch_id,status:value.status,received_at:receivedAt,rows};
}
function expectedProjection(kind,response,clock){
 const rows=response.rows.filter(row=>kind==='aircraft'?clock-row.time>=-60000&&clock-row.time<=120000:
  !row.stale&&clock-row.time>=0&&clock-row.time<=172800000).map(row=>[row.id,row.lat,row.lon]);
 rows.sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:0);
 return {count:rows.length,sha256:crypto.createHash('sha256').update(JSON.stringify(rows)).digest('hex')};
}
function validatePublicScene(scene,history,now){
 assert(scene&&scene.version===1&&scene.state==='synchronized','Public scene has not synchronized');
 for(const field of ['clock','rendered_at'])assert(Number.isFinite(scene[field])&&now-scene[field]>=-1000&&now-scene[field]<45000,'Public scene clock/frame stalled');
 const result={};
 for(const [kind,spec] of Object.entries(specs)){
  const shown=scene[kind],responses=history[kind];
  assert(shown&&!shown.failed&&['fresh','empty'].includes(shown.status),'Public hook is unavailable or failed');
  assert(Number.isFinite(shown.received_at)&&now-shown.received_at>=-1000&&now-shown.received_at<spec.cadence,'Public hook receipt stalled');
  assert(responses?.length&&now-responses.at(-1).received_at<spec.cadence,'Public network polling stalled');
  const match=responses.findLast(response=>response.batch_id===shown.batch_id&&response.status===shown.status&&
   Math.abs(response.received_at-shown.received_at)<15000&&
   expectedProjection(kind,response,scene.clock).sha256===shown.sha256&&expectedProjection(kind,response,scene.clock).count===shown.count);
  assert(match,'Rendered public batch/position projection differs from received response');
  result[kind]={batch_id:shown.batch_id,count:shown.count,sha256:shown.sha256,received_at:shown.received_at};
 }
 return result;
}
function assertFinalSampleGap(now,lastSample,limit=90){
 assert(Number.isFinite(now)&&Number.isFinite(lastSample)&&now>=lastSample&&now-lastSample<limit,'Final observation gap exceeded bound');
}
module.exports={captureProjection,expectedProjection,validatePublicScene,assertFinalSampleGap};
