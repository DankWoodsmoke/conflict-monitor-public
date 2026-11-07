from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import httpx
from app import main
from app.config import settings
from app.services import public_aircraft as pub
from app.services.opensky import normalize_adsb

NOW=datetime(2026,11,6,2,tzinfo=timezone.utc)


def payload():
    rows=normalize_adsb({'now':NOW.timestamp()*1000,'ac':[{'hex':'abc123','lat':29,'lon':44,'seen_pos':10,'flight':'TEST123','alt_baro':10000,'gs':300,'track':0,'category':'A3'}]},received=NOW.timestamp())['states']
    rows[0]['raw_text']='PRIVATE';rows[0]['aircraft_category']='military'
    return pub.prepare_snapshot(rows,{'source':'adsb.lol','status':'ok','source_timestamp':NOW.isoformat()},NOW)


def receipt():
    row=SimpleNamespace(source=pub.SOURCE,published_at=NOW,status='ok',payload=payload())
    row.id=pub.digest({'source':row.source,'published_at':NOW.isoformat(),'status':row.status,'payload':row.payload})
    return row


def test_independent_licensed_dataset_only_uses_exact_normalized_source_fields():
    row=receipt();response=pub.describe(row,NOW)
    ac=response['aircraft'][0]
    assert ac['lat']==29 and ac['lon']==44 and ac['heading']==0
    assert ac['heading_basis']=='course_over_ground' and ac['source']=='adsb.lol'
    assert not {'raw_text','aircraft_category','is_emergency','severity'}.intersection(ac)
    assert response['license']=='ODbL-1.0' and response['download_url'].endswith(row.id)
    assert len(response['coverage'])==4 and all(r['radius_nm']==250 for r in response['coverage'])
    download=pub.describe(row,NOW,download=True)
    assert download['payload']==row.payload and download['batch_id']==row.id
    assert pub.digest({k:download[k] for k in ('source','published_at','status','payload')})==row.id


def test_expiry_preserves_immutable_download_without_drawing_old_positions():
    row=receipt();now=NOW+timedelta(seconds=130)
    assert pub.describe(row,now)['status']=='stale' and pub.describe(row,now)['aircraft']==[]
    assert len(pub.describe(row,now,True)['payload']['aircraft'])==1


@pytest.mark.parametrize('state,source,stamp',[('ok','opensky',NOW.isoformat()),('failed','adsb.lol',NOW.isoformat()),('ok','adsb.lol',(NOW-timedelta(seconds=200)).isoformat())])
def test_unlicensed_or_unavailable_cache_never_becomes_public_empty_success(state,source,stamp):
    with pytest.raises(ValueError):pub.prepare_snapshot([],{'source':source,'status':state,'source_timestamp':stamp},NOW)


def test_corrupt_or_extra_private_fields_fail_readback():
    row=receipt();row.payload['aircraft'][0]['lat']=30
    with pytest.raises(ValueError,match='integrity'):pub.describe(row,NOW)
    row=receipt();row.payload['private_report']='do not expose'
    row.id=pub.digest({'source':row.source,'published_at':NOW.isoformat(),'status':row.status,'payload':row.payload})
    with pytest.raises(ValueError):pub.describe(row,NOW)


@pytest.mark.parametrize('duplicate', [True, False])
def test_digest_valid_older_writer_batch_requires_unique_aircraft_and_consistent_counts(duplicate):
    import copy
    row = receipt()
    row.payload['source_records'] += 1
    if duplicate:
        row.payload['aircraft'].append(copy.deepcopy(row.payload['aircraft'][0]))
    row.id=pub.digest({'source':row.source,'published_at':NOW.isoformat(),'status':row.status,'payload':row.payload})
    with pytest.raises(ValueError, match='Duplicate|reconcile'):
        pub.describe(row,NOW)


@pytest.mark.asyncio
async def test_exact_download_route_returns_expiry_instead_of_substituting_latest(monkeypatch):
    monkeypatch.setattr(settings,'public_read_only',True);monkeypatch.setattr(settings,'demo_mode',False)
    read=AsyncMock(return_value=None);monkeypatch.setattr(pub,'read_public_aircraft',read)
    identifier='a'*64
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://fixture') as client:
        response=await client.get('/publication/aircraft/download/'+identifier)
        assert response.status_code==410 and response.json()['status']=='expired_or_unavailable'
        assert (await client.get('/publication/aircraft?provider=private')).status_code==400
        assert (await client.get('/publication/aircraft/download/invalid')).status_code==403
    read.assert_awaited_once_with(identifier)
