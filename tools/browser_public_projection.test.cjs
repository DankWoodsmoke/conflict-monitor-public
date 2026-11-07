const {test}=require('node:test'),assert=require('node:assert/strict');
const {captureProjection,expectedProjection,validatePublicScene,assertFinalSampleGap,createGoogleTileCounters}=require('./browser_public_projection.cjs');
const now=Date.parse('2026-11-06T12:00:00Z');
function fixture(){
 const observation={lat:29,lon:44,ts:new Date(now-60000).toISOString()},aircraft={icao24:'abc123',lat:30,lon:45,observed_at:new Date(now-10000).toISOString()};
 const history={observations:[captureProjection('observations',{source:'nasa_firms_noaa20',status:'fresh',batch_id:'a'.repeat(64),hotspots:[observation]},now)],
  aircraft:[captureProjection('aircraft',{source:'adsb_lol',status:'fresh',batch_id:'b'.repeat(64),aircraft:[aircraft]},now)]};
 const scene={version:1,state:'synchronized',clock:now,rendered_at:now};
 for(const kind of ['observations','aircraft'])scene[kind]={batch_id:history[kind][0].batch_id,status:'fresh',failed:false,received_at:now,...expectedProjection(kind,history[kind][0],now)};
 return {history,scene};
}
test('matches actual public dataset receipt/digest without writing response positions',()=>{
 const {history,scene}=fixture();const result=validatePublicScene(scene,history,now);
 assert.equal(result.aircraft.count,1);assert.equal(result.observations.count,1);assert(!JSON.stringify(result).includes('lat'));
});
test('rejects old/tampered coordinates, wrong batch and failed hook despite healthy API',()=>{
 for(const mutate of [s=>s.aircraft.sha256='0'.repeat(64),s=>s.aircraft.batch_id='c'.repeat(64),s=>s.aircraft.failed=true,s=>s.aircraft.received_at=now-51000]){
  const {history,scene}=fixture();mutate(scene);assert.throws(()=>validatePublicScene(scene,history,now));
 }
 const {history,scene}=fixture();history.aircraft[0].rows[0].lon=46;assert.throws(()=>validatePublicScene(scene,history,now),/projection differs/);
});
test('accepts only legitimate scene-clock expiry subsets; retained expired points fail',()=>{
 const {history,scene}=fixture();history.aircraft[0].rows.push({id:'aircraft-def456',lat:31,lon:46,time:now-120001,stale:false});
 assert.equal(validatePublicScene(scene,history,now).aircraft.count,1);
 history.observations[0].rows.push({id:'thermal-expired',lat:31,lon:46,time:now-172800001,stale:false});
 assert.equal(validatePublicScene(scene,history,now).observations.count,1);
 scene.aircraft={...scene.aircraft,...expectedProjection('aircraft',history.aircraft[0],now-1000)};
 assert.throws(()=>validatePublicScene(scene,history,now),/projection differs/);
});
test('fails stalled network, stale rendered frame, missing diagnostics and missing final sample',()=>{
 const {history,scene}=fixture();history.aircraft[0].received_at=now-51000;assert.throws(()=>validatePublicScene(scene,history,now),/network polling stalled/);
 const next=fixture();next.scene.rendered_at=now-45000;assert.throws(()=>validatePublicScene(next.scene,next.history,now),/frame stalled/);
 assert.throws(()=>validatePublicScene(null,next.history,now));
 assertFinalSampleGap(14400,14370);assert.throws(()=>assertFinalSampleGap(14400,NaN));assert.throws(()=>assertFinalSampleGap(14400,14000));
});
test('precutoff request completed after three hours is raw evidence, not new tile work',()=>{
 const counters=createGoogleTileCounters(),request={};
 counters.request(request,10799999);counters.response(request,200,10800001);
 assert.equal(counters.counts.successful_responses_after_cutoff_raw,1);
 assert.equal(counters.counts.requests_after_cutoff,0);assert.equal(counters.counts.successful_requests_after_cutoff,0);
 assert.equal(counters.counts.requests_total,1);assert.equal(counters.counts.responses_total,1);
});
test('only matching successful postcutoff requests qualify; failures and unrelated responses do not',()=>{
 const counters=createGoogleTileCounters(),success={},failure={};
 counters.request(success,10800000);counters.request(failure,10800001);
 counters.response(success,206,10800003);counters.response(failure,503,10800004);counters.response({},200,10800005);
 assert.equal(counters.counts.requests_after_cutoff,2);assert.equal(counters.counts.successful_requests_after_cutoff,1);
 assert.equal(counters.counts.successful_responses_after_cutoff_raw,2);assert.equal(counters.counts.responses_total,3);
 counters.response(success,200,10800006);assert.equal(counters.counts.successful_requests_after_cutoff,1);
});
test('tile counters reject nonfinite clocks and do not admit preroot requests',()=>{
 const counters=createGoogleTileCounters(),request={};counters.request(request,null);counters.response(request,200,10800001);
 assert.equal(counters.counts.successful_requests_after_cutoff,0);
 assert.throws(()=>counters.request({},NaN),/Invalid Google request clock/);
});
