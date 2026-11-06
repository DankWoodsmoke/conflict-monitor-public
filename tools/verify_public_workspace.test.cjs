const test=require('node:test');
const assert=require('node:assert/strict');
const {inspectPublication,allowedApiPaths}=require('./verify_public_workspace.cjs');
const now=Date.parse('2026-11-06T03:00:00Z'),hash='a'.repeat(64);
function packet(kind){
  const common={source:kind==='observations'?'nasa_firms_noaa20':'adsb_lol',status:'fresh',batch_id:hash,published_at:new Date(now-30000).toISOString()};
  if(kind==='observations')return {...common,displayed_count:1,eligible_count:1,source_rows:10,regional_rows:2,
    hotspots:[{id:hash,lat:25,lon:40,ts:new Date(now-3600000).toISOString(),satellite:'NOAA-20',instrument:'VIIRS',frp:20,source_row_sha256:hash}]};
  return {...common,license:'ODbL-1.0',license_url:'https://opendatacommons.org/licenses/odbl/1-0/',coverage:[{},{},{},{}],
    aircraft:[{lat:25,lon:40,observed_at:new Date(now-30000).toISOString(),source:'adsb.lol',icao24:'abc123',normalized_record_sha256:hash}]};
}
test('closed mode rejects either populated publication and accepts explicit unavailable empty state',()=>{
  for(const kind of ['observations','aircraft']){
    const fresh=packet(kind);
    assert.throws(()=>inspectPublication(fresh,kind,false,now),/require CM_REQUIRE_PUBLIC_DATA/);
    const closed={...fresh,status:'awaiting_publication',batch_id:null,[kind==='observations'?'hotspots':'aircraft']:[]};
    assert.deepEqual(inspectPublication(closed,kind,false,now),{status:'awaiting_publication',count:0});
    closed.status='fresh';
    assert.throws(()=>inspectPublication(closed,kind,false,now));
  }
});
test('explicit data admission requires real nonempty fresh rows for both sources',()=>{
  for(const kind of ['observations','aircraft']){
    const fresh=packet(kind);
    assert.deepEqual(inspectPublication(fresh,kind,true,now),{status:'fresh',count:1,batch_id:hash,published_at:fresh.published_at});
    const rows=kind==='observations'?'hotspots':'aircraft';
    assert.throws(()=>inspectPublication({...fresh,[rows]:[]},kind,true,now),/empty/);
    assert.throws(()=>inspectPublication({...fresh,status:'stale'},kind,true,now),/not fresh/);
    assert.throws(()=>inspectPublication({...fresh,batch_id:'bad'},kind,true,now),/identity/);
    assert.throws(()=>inspectPublication({...fresh,source:'private_feed'},kind,true,now),/Unexpected public source/);
    assert.throws(()=>inspectPublication({...fresh,raw_text:'private'},kind,true,now),/Private fields/);
  }
});
test('unusable coordinates, stale clocks and inferred fields cannot qualify Earth data',()=>{
  for(const kind of ['observations','aircraft'])for(const bad of [{lat:91},{lon:NaN},{summary:'inferred'},{[kind==='observations'?'ts':'observed_at']:new Date(now-49*3600000).toISOString()}]){
    const fresh=packet(kind),key=kind==='observations'?'hotspots':'aircraft';
    fresh[key][0]={...fresh[key][0],...bad};
    assert.throws(()=>inspectPublication(fresh,kind,true,now));
  }
});
test('provider attribution, selection and provenance are required',()=>{
  const nasa=packet('observations');nasa.hotspots[0].frp=9;
  assert.throws(()=>inspectPublication(nasa,'observations',true,now),/provenance/);
  const air=packet('aircraft');air.license_url='https://example.invalid/';
  assert.throws(()=>inspectPublication(air,'aircraft',true,now),/license/);
  air.license_url='https://opendatacommons.org/licenses/odbl/1-0/';air.aircraft[0].source='opensky';
  assert.throws(()=>inspectPublication(air,'aircraft',true,now),/provenance/);
});
test('different source IDs cannot hide an equivalent thermal position/time',()=>{
  const nasa=packet('observations');nasa.displayed_count=2;nasa.eligible_count=2;
  nasa.hotspots.push({...nasa.hotspots[0],id:'b'.repeat(64),ts:'2026-11-05T21:00:00-05:00',frp:30});
  assert.throws(()=>inspectPublication(nasa,'observations',true,now),/position\/time/);
  nasa.hotspots[1].lat=26;assert.equal(inspectPublication(nasa,'observations',true,now).count,2);
});
test('page polling permission is exact, capability-bound and excludes private or download APIs',()=>{
  assert.deepEqual([...allowedApiPaths({})],['/api/config','/api/status']);
  assert.deepEqual([...allowedApiPaths({public_observations_enabled:true})],['/api/config','/api/status','/api/publication/observations']);
  const paths=allowedApiPaths({public_observations_enabled:true,public_aircraft_enabled:true,public_reports_enabled:true,public_tracking_enabled:true});
  assert.equal(paths.size,4);
  for(const route of ['/api/events','/api/tracking/aircraft','/api/publication/aircraft/download/'+hash,'/api/publication/observations/','/api/market','/api/costs'])assert.equal(paths.has(route),false);
});
