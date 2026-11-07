const test=require('node:test');
const assert=require('node:assert/strict');
const {inspectAircraftCoverage}=require('./verify_mobile_earth.cjs');
const now=Date.parse('2026-11-06T04:00:00Z');
function fixture(){return {status:'ok',source:'adsb.lol',count:5,cache_age_seconds:10,
 regions:[['levant',33,35],['gulf',25,54],['iran_iraq',33,48],['red_sea',18,41]].map(([id,lat,lon])=>({id,lat,lon,radius_nm:250,status:'ok',error:null,last_success_at:new Date(now-60000).toISOString(),cache_age_seconds:60}))};}
test('real successful bounded regional receipts qualify with explicit partial coverage limit',()=>{
 const result=inspectAircraftCoverage(fixture(),now);assert.equal(result.regions.length,4);assert.match(result.limitation,/coverage is incomplete/);
});
test('four configured regions alone never qualify failed, uncollected, duplicated or expired source coverage',()=>{
 for(const mutate of [p=>p.status='stale',p=>p.source='synthetic',p=>p.cache_age_seconds=46,p=>p.regions[0].status='not_collected',p=>p.regions[0].status='failed',p=>p.regions[0].last_success_at=null,p=>p.regions[0].last_success_at=new Date(now-200000).toISOString(),p=>p.regions[0].cache_age_seconds=181,p=>p.regions[0].id='gulf',p=>p.regions[0].radius_nm=500]){
  const data=fixture();mutate(data);assert.throws(()=>inspectAircraftCoverage(data,now));
 }
});
