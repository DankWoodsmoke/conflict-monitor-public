import type { ConflictEvent } from "../types/event";

/** Fixed content, deterministic IDs and geometry; only the explicit reference clock varies. */
export function buildShowcase(asOf: number) {
  const iso = (minutes: number) => new Date(asOf - minutes * 60_000).toISOString();
  const locations = [
    ["Muscat exercise sector", 23.59, 58.41], ["Gulf demonstration corridor", 26.60, 56.50],
    ["Doha exercise sector", 25.29, 51.53], ["Amman exercise sector", 31.95, 35.93],
    ["Nicosia exercise sector", 35.18, 33.38], ["Beirut exercise sector", 33.89, 35.50],
    ["Alexandria exercise sector", 31.20, 29.92], ["Red Sea exercise corridor", 20.04, 38.90],
    ["Baghdad exercise sector", 33.32, 44.37], ["Ankara exercise sector", 39.93, 32.86],
    ["Riyadh exercise sector", 24.71, 46.68], ["Kuwait exercise sector", 29.38, 47.98],
  ] as const;
  const scenarios = [
    ["military", "Exercise: simulated aircraft activity reported; mission and intent remain unknown.", 7],
    ["economic", "Exercise: fictional shipping delay prompts a port-capacity assessment.", 5],
    ["diplomatic", "Exercise: fictional mediation meeting scheduled; no outcome has been established.", 3],
    ["humanitarian", "Exercise: a simulated aid convoy reaches its designated logistics hub.", 4],
    ["thermal_anomaly", "Exercise: synthetic thermal hotspot overlaps an industrial site; cause undetermined.", 6],
    ["cyber", "Exercise: a fictional network outage is reported; attribution remains unresolved.", 5],
    ["protest", "Exercise: a simulated public assembly is reported by one demonstration source.", 2],
    ["military", "Exercise: a repeated vessel-movement claim circulates; copies are not corroboration.", 6],
  ] as const;
  const events: ConflictEvent[] = Array.from({ length: 72 }, (_, i) => {
    const loc = locations[i % locations.length];
    const scenario = scenarios[i % scenarios.length];
    const reviewed = i % 7 === 0;
    return {
      id: 900001 + i, source: ["telegram", "rss_x_demo", "rss_demo_wire"][i % 3],
      channel_name: ["Demo Observer", "Demo Analyst", "Demo Dispatch"][i % 3],
      raw_text: `[SYNTHETIC EXERCISE] ${scenario[1]} Record ${i + 1}. No real incident is represented.`,
      summary: scenario[1], event_type: scenario[0], severity: scenario[2],
      lat: i === 9 ? null : loc[1] + Math.floor(i / 12) * .035,
      lon: i === 9 ? null : loc[2] + Math.floor(i / 12) * .03,
      timestamp: iso(i * 18 + 4), created_at: iso(i * 18 + 2),
      report_count: i % 8 === 7 ? 6 : reviewed ? 2 : 1,
      reporting_channels: reviewed ? "Demo Observer, Demo Dispatch" : "Demo Observer",
      location_name: i === 9 ? "Unresolved exercise location" : loc[0],
      source_url: `https://example.org/exercise/reports/${i + 1}`,
      source_reliability: null, confirmed_networks: "",
      military_subtype: scenario[0] === "military" ? "naval" : "",
      actor: "Fictional exercise participant", casualties: "",
      anomaly_score: i % 9 === 0 ? 8 : 0,
      anomaly_analysis: i % 9 === 0 ? "Synthetic anomaly: unusual relative to this exercise baseline; not a threat prediction." : "",
      synthetic: true,
      evidence: {status: reviewed ? "multiple_reports" : "reported", unique_source_count:reviewed?2:1,
        source_networks:[], independent_origin_count:null, independence_status:"unassessed", verification_basis:"none",
        limitations:["Synthetic fixture. No factual verification or independent origin assessment."]},
      classification_status:"extracted", geolocation_precision:i===9 ? "unknown" : "city",
    };
  });
  const aircraft = Array.from({ length: 10 }, (_, i) => ({
    icao24: `demo${String(i).padStart(2, "0")}`, callsign: `DEMO ${String(i + 1).padStart(2, "0")}`,
    origin_country: "Synthetic exercise", lat: 23.7 + i * 1.12, lon: 34.5 + i * 2.16,
    altitude: 6500 + i * 350, velocity: 180 + i * 7, heading: 32 + i * 24,
    on_ground: false, position_source: 0, type: "DEMO", registration: "SYNTHETIC",
    aircraft_category: "unknown", synthetic: true,
  }));
  const vessels = Array.from({ length: 6 }, (_, i) => ({
    mmsi: `00000000${i}`, name: `EXERCISE VESSEL ${i + 1}`, lat: 24.4 + i * .43,
    lon: 57.0 + i * .32, speed: 9 + i, heading: 65 + i * 18, course: 65 + i * 18,
    nav_status: 0, ship_type: 70, ship_type_name: "Synthetic cargo track", destination: "DEMO PORT",
    vessel_category: "cargo", synthetic: true,
  }));
  const jamming = [{ lat: 30.1, lon: 40.2, radius_km: 45, aircraft_count: 3, intensity: .35,
    assessment: "synthetic navigation-quality anomaly; interference unverified", synthetic: true }];
  const sitrep = {
    id: 9001, generated_at: iso(6), period_start: iso(360), period_end: iso(6),
    headline: "EXERCISE / A fictional corridor, multiple claims, one inspectable evidence trail",
    situation: "This deterministic demonstration connects reports, geospatial context and competing explanations. Every incident, track and market value is synthetic. A shipping-delay report remains separate from a circulating military claim. [src:900001,900002]",
    escalation_level: "ELEVATED", escalation_score: 38, events_analyzed: events.length,
    escalation_text: "Exercise assessment only. Increased reporting volume can reflect duplication or source coverage. It does not establish a change in real-world risk. [src:900008]",
    economic_exposure: "Scenario assumption: reduced corridor throughput could affect logistics. The displayed market prices are fabricated test values, not investment information. [src:900002]",
    game_theory: "Competing hypotheses: routine scheduling, precautionary repositioning, and deliberate signaling. The current exercise observations cannot discriminate among them. [src:900001]",
    humanitarian_ground: "The aid-convoy item is a fictional logistics record. No estimate of casualties or affected population can be derived from it. [src:900004]",
    historical_analogue: "Analogy is a prompt for investigation, not evidence. Compare mechanisms and disconfirming observations before importing an earlier outcome.",
    key_questions: JSON.stringify([{q:"Are the reports independent?",a:"Count original observations and transmission lineage, not publishers or political groupings. Two demonstration records retain separate original report metadata. [src:900001]",watch:"A second original record with compatible time, place and claim."},{q:"What would change this assessment?",a:"A contradictory primary record or a validated timing/location correction would require revision.",watch:"Record the correction and preserve the earlier assessment."}]),
    key_developments: JSON.stringify(events.slice(0, 5).map(e => ({text:e.summary, event_ids:[e.id]}))),
    event_ids: events.slice(0,12).map(e => e.id).join(","), synthetic: true,
  };
  const market = { stale: false, cached_ago: 0, synthetic: true, data: [
    ["DEMO-OIL","OIL / DEMO",84.20,1.25,"commodity"], ["DEMO-GOLD","GOLD / DEMO",2410,-.42,"commodity"],
    ["DEMO-VIX","VOL / DEMO",19.3,.65,"fear"], ["DEMO-INDEX","INDEX / DEMO",5200,.35,"equity"],
  ].map(([symbol,name,price,change_pct,category]) => ({symbol,name,price,change_pct,category,unit:"USD",change_abs:0,market_state:"SYNTHETIC"})) };
  const snapshots = Array.from({ length: 25 }, (_, i) => ({
    ts: iso((24-i)*60), aircraft: aircraft.map(a => ({ i:a.icao24,c:a.callsign,la:a.lat,lo:a.lon-(24-i)*.035,a:a.altitude,h:a.heading,v:a.velocity,t:a.type,k:a.aircraft_category,e:false,s:"" })),
    vessels: vessels.map(v => ({m:v.mmsi,n:v.name,la:v.lat,lo:v.lon-(24-i)*.007,sp:v.speed,h:v.heading,k:v.vessel_category,f:"",st:v.ship_type_name})),
    jamming: jamming.map(j => ({la:j.lat,lo:j.lon,r:j.radius_km,c:j.aircraft_count,i:j.intensity})),
  }));
  const orbits = Array.from({length:4},(_,i) => ({
    name:`EXERCISE ORBIT ${i+1}`,norad_id:String(900000001+i),synthetic:true,
    epoch:new Date(asOf).toISOString(),epoch_age_hours:0,source:"synthetic-exercise",
    omm:{OBJECT_NAME:`EXERCISE ORBIT ${i+1}`,OBJECT_ID:`DEMO-${i+1}`,EPOCH:new Date(asOf).toISOString(),
      MEAN_MOTION:14.9+i*.1,ECCENTRICITY:.0003,INCLINATION:48+i*8,RA_OF_ASC_NODE:30+i*45,
      ARG_OF_PERICENTER:60,MEAN_ANOMALY:90+i*30,EPHEMERIS_TYPE:0 as const,CLASSIFICATION_TYPE:"U" as const,
      NORAD_CAT_ID:900000001+i,ELEMENT_SET_NO:1,REV_AT_EPOCH:1,BSTAR:.0001,MEAN_MOTION_DOT:0,MEAN_MOTION_DDOT:0},
  }));
  const hotspots=[{lat:27.8,lon:52.6,frp:22,conf:null,confidence_label:"nominal",ts:iso(38),synthetic:true,
    google_maps_url:"",copernicus_url:"",wms_thumbnail:"",gibs_viirs_thumb:"",gibs_modis_thumb:"",gibs_landsat_thumb:"",
    eo_browser_url:"",landsatlook_url:"",planet_url:"",probable_flare:false,flare_zone:"",matched:false,proximity_matches:[]}];
  return { events, aircraft, vessels, jamming, sitrep, market, snapshots, orbits, hotspots, asOf: new Date(asOf).toISOString() };
}

const requestedClock = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("asOf");
const parsedClock = requestedClock ? Date.parse(requestedClock) : NaN;
export const showcase = buildShowcase(Number.isFinite(parsedClock) ? parsedClock : Math.floor(Date.now() / 60_000) * 60_000);

export function showcaseResponse(url: URL): unknown {
  const path = url.pathname.replace(/^\/api(?=\/)/, "").replace(/\/$/, "");
  if (path === "/config") return { demo_mode:true, showcase:true, ingestion_enabled:false };
  if (path === "/events/time-range") return { earliest:showcase.events[showcase.events.length - 1].timestamp, latest:showcase.events[0].timestamp };
  if (path === "/events/batch") return showcase.events.filter(e => (url.searchParams.get("ids") || "").split(",").includes(String(e.id)));
  if (path === "/events" || path === "/events/anomalies") {
    const after = Date.parse(url.searchParams.get("after") || "");
    const before = Date.parse(url.searchParams.get("before") || "");
    const beforeId=Number(url.searchParams.get("before_id"))||null;
    return showcase.events.filter(e => (!Number.isFinite(after) || Date.parse(e.timestamp)>=after) &&
      (!Number.isFinite(before) || (beforeId==null ? Date.parse(e.timestamp)<=before : Date.parse(e.timestamp)<before||(Date.parse(e.timestamp)===before&&e.id<beforeId))) &&
      (!url.searchParams.get("event_type") || e.event_type===url.searchParams.get("event_type")) &&
      (path!=="/events/anomalies" || (e.anomaly_score||0)>=7)).slice(0,Number(url.searchParams.get("limit"))||500);
  }
  if (/^\/events\/\d+\/imagery$/.test(path)) return {s2_thumbnail:"", imagery_status:"not_available_in_synthetic_exercise"};
  if (path === "/tracking/aircraft") return showcase.aircraft;
  if (path === "/tracking/vessels") return showcase.vessels;
  if (path === "/tracking/jamming") return showcase.jamming;
  if (path === "/tracking/tle") return showcase.orbits;
  if (path === "/tracking/snapshots") return showcase.snapshots;
  if (path === "/satellite/hotspots") return {hotspots:showcase.hotspots, synthetic:true};
  if (path === "/market") return showcase.market;
  if (path === "/costs/summary") return {avg_per_day_usd:0,total_spend_usd:0,days_running:1,breakdown:{},synthetic:true};
  if (path === "/sitreps") return [showcase.sitrep,{...showcase.sitrep,id:9000,generated_at:showcase.events[18].timestamp}];
  if (/^\/sitreps\/\d+\/events$/.test(path)) return showcase.events.slice(0,12);
  if (path === "/sitreps/latest") return {sitrep:showcase.sitrep};
  if (/^\/sitreps\/\d+$/.test(path)) return {...showcase.sitrep,id:Number(path.split("/").pop())};
  if (path === "/videos/manifest.json") return {};
  return undefined;
}
