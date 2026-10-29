"""Bounded, read-only live observation; emits metadata, never source/key bodies."""
import argparse
import asyncio
import hashlib
import json
import math
import socket
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import websockets


def stamp():
    return datetime.now(timezone.utc).isoformat()


def finite_coordinates(row):
    lat, lon = row.get("lat"), row.get("lon")
    if lat is None or lon is None:
        return lat is None and lon is None
    return all(not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v) for v in (lat,lon)) and -90<=lat<=90 and -180<=lon<=180


def valid_event_payload(payload):
    if not isinstance(payload,dict) or payload.get("type") != "new_event":
        return False
    event = payload.get("event")
    return isinstance(event,dict) and type(event.get("id")) is int and event["id"] > 0 and isinstance(event.get("raw_text"),str) and finite_coordinates(event)


def provider_summary(status):
    allowed = {"status","count","record_count","data_age_seconds","data_stale","cache_age_seconds",
        "observation_age_seconds","publication_age_seconds","publication_stale","observations_stale",
        "observation_count","connected","poll_in_progress","association_truncated"}
    output = {}
    for key in ("aircraft","maritime","satellites","thermal_observations","telegram"):
        value=status.get(key,{})
        output[key]={k:v for k,v in value.items() if k in allowed and isinstance(v,(str,int,float,bool,type(None)))}
    output["rss"]=[{k:v for k,v in row.items() if k in allowed|{"source","publication_in_future"}}
        for row in status.get("news_feeds",{}).get("feeds",[])]
    output["workers"]={name:row.get("state") for name,row in status.get("workers",{}).items()}
    return output


def deployment_identity(value, expected_containers, database_container):
    """Keep only reviewed identity metadata; never persist inspect environments."""
    rows = [json.loads(line) for line in value.splitlines() if line.strip()]
    if (len(rows) != len(expected_containers)
        or any(not isinstance(row, dict) or not isinstance(row.get('name'), str) for row in rows)
        or {row['name'].lstrip('/') for row in rows} != set(expected_containers)):
        raise ValueError('Incomplete deployment identity')
    identities = []
    for row in rows:
        name = row['name'].lstrip('/')
        if not all(isinstance(row.get(key), str) and row[key] for key in ('image', 'started_at')):
            raise ValueError('Invalid container identity')
        safe = {'name': name, 'image': row['image'], 'started_at': row['started_at']}
        if name == database_container:
            safe['pgdata'] = [{key: mount.get(key) for key in ('Type', 'Name', 'Destination')}
                for mount in row.get('mounts', []) if mount.get('Destination') == '/var/lib/postgresql/data']
        identities.append(safe)
    identities.sort(key=lambda row: row['name'])
    text = '\n'.join('|'.join((row['name'], row['image'], row['started_at'],
        json.dumps(row.get('pgdata', []), sort_keys=True))) for row in identities)
    return {'identity': text, 'containers': identities}


SQL = """SELECT json_build_object(
'postgresql_version',current_setting('server_version'),
'postgis_version',postgis_lib_version(),
'collation_version_matches',(SELECT datcollversion IS NOT DISTINCT FROM pg_database_collation_actual_version(oid) FROM pg_database WHERE datname=current_database()),
'events',(SELECT count(*) FROM events),
'receipts',(SELECT count(*) FROM source_reports),
'pending_receipts_over_5m',(SELECT count(*) FROM source_reports WHERE status='received' AND received_at<NOW()-INTERVAL '5 minutes'),
'synthetic_events',(SELECT count(*) FROM events WHERE source IN ('demo','synthetic','simulation')),
'invalid_positions',(SELECT count(*) FROM events WHERE (lat IS NULL)<>(lon IS NULL) OR lat NOT BETWEEN -90 AND 90 OR lon NOT BETWEEN -180 AND 180),
'position_geometry_mismatch',(SELECT count(*) FROM events WHERE (geometry IS NULL)<>(lat IS NULL) OR (geometry IS NOT NULL AND (ST_SRID(geometry)<>4326 OR ST_X(geometry)<>lon OR ST_Y(geometry)<>lat))),
'duplicate_channel_message_ids',(SELECT count(*) FROM (SELECT source,channel_name,telegram_message_id FROM events WHERE telegram_message_id IS NOT NULL GROUP BY source,channel_name,telegram_message_id HAVING count(*)>1) d),
'checkpoint_behind_stored_message',(SELECT count(*) FROM (SELECT channel_name,max(telegram_message_id) max_id FROM events WHERE source='telegram' AND telegram_message_id IS NOT NULL GROUP BY channel_name) e LEFT JOIN channel_checkpoints c USING(channel_name) WHERE c.last_message_id IS NULL OR c.last_message_id<e.max_id),
'usage_calls',(SELECT count(*) FROM usage_log),
'snapshots',(SELECT count(*) FROM tracking_snapshots));"""


async def subprocess_output(arguments, timeout=15):
    process=await asyncio.create_subprocess_exec(*arguments,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        stdout,stderr=await asyncio.wait_for(process.communicate(),timeout=timeout)
        return process.returncode,stdout.decode("utf8","replace")
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return -1,""


async def run(args):
    parsed=urlsplit(args.base_url)
    if parsed.hostname not in {"127.0.0.1","localhost"} or parsed.scheme!="http":
        raise ValueError("This observer is limited to the local deployment")
    if not 60<=args.seconds<=14400 or not 10<=args.interval<=300:
        raise ValueError("Use a bounded1-minute to4-hour observation and10–300s interval")
    directory=Path(args.output)
    if any((directory/name).exists() for name in ("summary.json","samples.jsonl","websocket.jsonl")):
        raise ValueError("Output contains an earlier observation; choose a fresh output directory")
    directory.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    summary={"started_at":stamp(),"scope":"bounded_read_only_live_observation","requested_seconds":args.seconds,
        "observer_version":3,"observer_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"interval_seconds":args.interval,
        "base_url":args.base_url,"samples":0,"http_errors":0,"integrity_findings":0,"source_hash_changes":0,
        "ws_connects":0,"ws_disconnects":0,"ws_messages":0,"ws_payload_errors":0,"deployment_segments":[],
        "expected_containers":{"backend":args.backend_container,"frontend":args.frontend_container,"database":args.database_container},
        "expected_database":{"postgresql":args.expected_postgresql,"postgis":args.expected_postgis,"data_volume":args.expected_data_volume},
        "status":"running","limitations":["Provider clocks/metadata and sampled application behavior, not factual truth.",
        "A deployment change creates a new segment; total elapsed time is not a final-image-only soak.",
        "No physical device, arbitrary video playback, or every code path is certified."]}
    latest_ids={}
    event_hashes={}
    stop=asyncio.Event()
    def append(name,row):
        with (directory/name).open("a",encoding="utf8") as f:f.write(json.dumps(row,ensure_ascii=True)+"\n")
    def save():
        temporary=directory/"summary.tmp"
        temporary.write_text(json.dumps(summary,indent=2),encoding="utf8")
        for attempt in range(6):
            try:
                temporary.replace(directory/"summary.json")
                return
            except PermissionError:
                # Windows readers can briefly hold a replace-incompatible handle.
                # Preserve the last complete progress file and retry boundedly.
                if attempt == 5:
                    raise
                time.sleep(.02 * (attempt + 1))
    async def socket_watch():
        url=args.base_url.replace("http://","ws://").rstrip("/")+"/api/ws/events"
        while not stop.is_set():
            try:
                async with websockets.connect(url,origin=args.base_url,max_size=2_000_000,open_timeout=10) as ws:
                    summary["ws_connects"]+=1
                    append("websocket.jsonl",{"at":stamp(),"event":"connected"})
                    while not stop.is_set():
                        try:raw=await asyncio.wait_for(ws.recv(),timeout=10)
                        except asyncio.TimeoutError:continue
                        try:
                            payload=json.loads(raw)
                        except (ValueError,TypeError,RecursionError):
                            summary["ws_payload_errors"]+=1
                            continue
                        if not valid_event_payload(payload):
                            summary["ws_payload_errors"]+=1
                            continue
                        event=payload["event"]
                        summary["ws_messages"]+=1
                        latest_ids[event.get("id")]=hashlib.sha256(str(event.get("raw_text","")).encode()).hexdigest()
                        if len(latest_ids)>5000:latest_ids.pop(next(iter(latest_ids)))
            except asyncio.CancelledError:raise
            except Exception as exc:
                summary["ws_disconnects"]+=1
                append("websocket.jsonl",{"at":stamp(),"event":"disconnected","error_type":type(exc).__name__})
                try:await asyncio.wait_for(stop.wait(),timeout=3)
                except asyncio.TimeoutError:pass
    watcher=asyncio.create_task(socket_watch())
    save()
    try:
        async with httpx.AsyncClient(base_url=args.base_url,timeout=10,follow_redirects=True) as client:
            previous_segment=None
            sample=0
            while time.monotonic()-started<args.seconds:
                tick=time.monotonic()
                row={"at":stamp(),"elapsed_seconds":round(tick-started,2),"sample":sample,"requests":{},"findings":[]}
                responses={}
                for endpoint in ("/api/health","/api/status","/api/events?limit=50","/api/tracking/aircraft","/api/tracking/vessels",
                                 "/api/tracking/tle","/api/satellite/hotspots","/api/sitreps/latest"):
                    now=time.monotonic()
                    try:
                        response=await client.get(endpoint)
                        row["requests"][endpoint]={"status":response.status_code,"ms":round((time.monotonic()-now)*1000,2)}
                        if response.status_code!=200:summary["http_errors"]+=1
                        else:responses[endpoint]=response.json()
                    except Exception as exc:
                        summary["http_errors"]+=1
                        row["requests"][endpoint]={"error_type":type(exc).__name__}
                row["providers"]=provider_summary(responses.get("/api/status",{}))
                events=responses.get("/api/events?limit=50",[])
                row["sampled_event_count"]=len(events)
                row["sampled_source_counts"]=dict(Counter(e.get("source") for e in events))
                for event in events:
                    event_id=event.get("id")
                    digest=hashlib.sha256(str(event.get("raw_text","")).encode()).hexdigest()
                    if event_id in event_hashes and event_hashes[event_id]!=digest:
                        summary["source_hash_changes"]+=1
                        row["findings"].append({"kind":"existing_raw_text_changed","event_id":event_id})
                    event_hashes[event_id]=digest
                    if not finite_coordinates(event):row["findings"].append({"kind":"invalid_event_coordinates","event_id":event_id})
                    if event_id in latest_ids and latest_ids[event_id]!=digest:
                        row["findings"].append({"kind":"websocket_rest_raw_hash_mismatch","event_id":event_id})
                for endpoint in ("/api/tracking/aircraft","/api/tracking/vessels"):
                    records=responses.get(endpoint,[])
                    if isinstance(records,list):
                        invalid=sum(not finite_coordinates(e) for e in records)
                        row[endpoint]={"count":len(records),"invalid_coordinates":invalid}
                        if invalid:row["findings"].append({"kind":"invalid_tracking_coordinates","endpoint":endpoint,"count":invalid})
                if sample%2==0:
                    code,value=await subprocess_output(["docker","stats","--no-stream","--format","{{json .}}",args.backend_container,args.frontend_container,args.database_container])
                    if code==0:
                        row["container_resources"]=[{k:v for k,v in json.loads(line).items() if k in {"Name","CPUPerc","MemUsage","MemPerc","PIDs","NetIO","BlockIO"}} for line in value.splitlines() if line.strip()]
                    expected=[args.backend_container,args.frontend_container,args.database_container]
                    format_json='{"name":{{json .Name}},"image":{{json .Image}},"started_at":{{json .State.StartedAt}},"mounts":{{json .Mounts}}}'
                    code,value=await subprocess_output(["docker","inspect","--format",format_json,*expected])
                    if code==0:
                        try:
                            identity=deployment_identity(value,expected,args.database_container)
                            row['deployment_identity']=identity
                            segment=identity['identity']
                            if segment!=previous_segment:
                                info={"at":stamp(),"elapsed_seconds":row["elapsed_seconds"],**identity}
                                summary["deployment_segments"].append(info)
                                append("segments.jsonl",info)
                                previous_segment=segment
                        except (ValueError,TypeError,KeyError):
                            row['deployment_identity']={'status':'unavailable'}
                    else:
                        row['deployment_identity']={'status':'unavailable','exit_code':code}
                if sample%10==0:
                    code,value=await subprocess_output(["docker","exec",args.database_container,"psql","-U","monitor","-d","conflict_monitor","-t","-A","-c",SQL])
                    if code==0:
                        integrity=json.loads(value.strip())
                        row["sql_integrity"]=integrity
                        for name in ("invalid_positions","position_geometry_mismatch","duplicate_channel_message_ids","checkpoint_behind_stored_message","synthetic_events"):
                            if integrity.get(name):row["findings"].append({"kind":name,"count":integrity[name]})
                    else:row["sql_integrity"]={"status":"unavailable","exit_code":code}
                summary["samples"]+=1
                summary["integrity_findings"]+=len(row["findings"])
                summary["last_sample_at"]=row["at"]
                summary["elapsed_seconds"]=round(time.monotonic()-started,2)
                append("samples.jsonl",row)
                save()
                sample+=1
                delay=min(args.interval-(time.monotonic()-tick),args.seconds-(time.monotonic()-started))
                if delay>0:await asyncio.sleep(delay)
        # Completion is an observation state. The independent assessor checks
        # duration, coverage, SQL availability and socket uptime before qualifying.
        summary["status"]="completed_with_findings" if summary["http_errors"] or summary["integrity_findings"] or summary["ws_payload_errors"] else "observation_completed"
    finally:
        stop.set()
        watcher.cancel()
        await asyncio.gather(watcher,return_exceptions=True)
        summary["ended_at"]=stamp()
        summary["elapsed_seconds"]=round(time.monotonic()-started,2)
        save()
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--base-url",default="http://127.0.0.1:5190")
    parser.add_argument("--seconds",type=int,default=3600)
    parser.add_argument("--interval",type=int,default=30)
    parser.add_argument("--output",default="artifacts/live-soak")
    parser.add_argument("--backend-container",default="cmonitor-live-backend-1")
    parser.add_argument("--frontend-container",default="cmonitor-live-frontend-1")
    parser.add_argument("--database-container",default="cmonitor-live-db-1")
    parser.add_argument("--expected-postgresql")
    parser.add_argument("--expected-postgis")
    parser.add_argument("--expected-data-volume")
    asyncio.run(run(parser.parse_args()))
