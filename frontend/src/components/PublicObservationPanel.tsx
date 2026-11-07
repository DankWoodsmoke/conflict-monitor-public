import type {PublicObservations} from "../hooks/usePublicObservations";
import {API_BASE} from "../lib/runtime";
import {utc} from "../lib/earth";
import type {PublicAircraft} from "../hooks/usePublicAircraft";

export function PublicDataAttribution({aircraft}:{aircraft:PublicAircraft|null}){
 const id=aircraft?.batch_id;
 return <div className="public-scope-note public-data-attribution">Thermal: NASA FIRMS · ADS-B: <a href="https://www.adsb.lol/docs/open-data/api" target="_blank" rel="noreferrer">adsb.lol</a> · <a href="https://opendatacommons.org/licenses/odbl/1-0/" target="_blank" rel="noreferrer">ODbL 1.0</a>{id&&/^[a-f0-9]{64}$/.test(id)&&<> · <a href={`${API_BASE}/publication/aircraft/download/${id}`}>Download ADS-B dataset</a></>} · Partial coverage</div>;
}

export function PublicObservationPanel({data,failed,aircraft,aircraftFailed}:{data:PublicObservations|null;failed:boolean;aircraft?:PublicAircraft|null;aircraftFailed?:boolean}){
 const label=failed?"Publication unavailable":!data?"Loading published observations":({fresh:"Thermal observations available",empty:"No observations in this publication window",stale:"Retained thermal observations · stale",awaiting_publication:"Awaiting first publication",failed:"Source collection failed"}[data.status]||"Publication unavailable");
 return <section className="public-empty-state public-observation-panel" aria-label="Public thermal observations">
  <span>INDEPENDENT PUBLIC DATASETS</span><h2>Reported ADS-B positions</h2><p>{aircraftFailed?"ADS-B publication request failed; positions withheld":!aircraft?"Loading publication":aircraft.status==="fresh"?`${aircraft.aircraft.length} positions in the latest published snapshot`:aircraft.status==="empty"?"No unexpired positions in this snapshot; coverage is incomplete":aircraft.status==="stale"?"Publication stale; expired positions hidden":aircraft.status==="failed"?"No fresh licensed collector cache available":"Awaiting first ADS-B publication"}</p>
  <p>Aircraft and surface-emitter broadcasts. Four 250-nautical-mile query regions: Eastern Mediterranean, Persian Gulf, Iran/Iraq and Red Sea. Observations expire after 120 seconds. Surface projections; identity, ownership, mission and intent are unverified.</p>
  {aircraft?.published_at&&<dl><dt>Published</dt><dd>{utc(aircraft.published_at)}</dd><dt>Source records / filtered</dt><dd>{aircraft.source_records??"Unknown"} / {aircraft.filtered_records??"Unknown"}</dd></dl>}
  <span>NASA LANCE / FIRMS · NOAA-20 VIIRS</span><h2>{label}</h2>
  <p role="status">{failed?"The latest request failed. Map observations are withheld until retrieval recovers.":"Thermal pixels provide geographic context. They do not identify strikes, causes, actors or casualties."}</p>
  {data?.published_at&&<dl><dt>Published</dt><dd>{utc(data.published_at)}</dd><dt>Latest collection attempt</dt><dd>{data.last_attempt_status}</dd><dt>Map selection</dt><dd>{data.displayed_count} of {data.eligible_count} eligible pixels</dd><dt>Source selection</dt><dd>{data.regional_rows??"Unknown"} regional rows from {data.source_rows??"Unknown"} downloaded rows</dd></dl>}
  {data?.last_attempt_status==="failed"&&data.published_at&&<p>Latest collection failed. The retained batch keeps its original acquisition and publication times.</p>}
  <p>25°E–65°E / 10°N–42°N · acquisition within 48 hours · FRP ≥10 MW. At most 2,000 pixels, highest power first; power is not impact severity. Collection every 3 hours; stale after 12 hours.</p>
  <p>Clouds, overpass timing and display filters leave gaps. Empty coverage is not evidence of no activity.</p>
  <p><a href="https://www.earthdata.nasa.gov/data/projects/lance#ed-firms-citation" target="_blank" rel="noreferrer">NASA citation</a>{" · "}<a href="https://nrt4.modaps.eosdis.nasa.gov/api/v2/content/archives/FIRMS/README.pdf" target="_blank" rel="noreferrer">Source disclaimer</a>{data?.batch_id&&/^[a-f0-9]{64}$/.test(data.batch_id)&&<> · <a href={`${API_BASE}/publication/observations/download/${data.batch_id}`}>Download this NASA dataset</a></>}</p>
  <h3>Reports withheld</h3><p>Private publisher reports, Telegram content and generated briefings are not included in this public dataset.</p>
 </section>;
}
