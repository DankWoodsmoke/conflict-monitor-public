"""Restart qualification must reject byte loss and never infer an unobserved restart."""
import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("restart_verifier", Path(__file__).resolve().parents[2] / "tools/verify_restart_persistence.py")
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def snapshots():
    before = {"observed_at": "before", "container": {"image": "same-image", "started_at": "start1"},
        "database": {"events": {"1": "source-hash"}, "source_reports": {"receipt": "content-hash"},
                     "checkpoints": {"public-channel": 123}, "usage_rows": 0},
        "video": {"filename": "fixture.mp4", "sha256": "full-hash", "bytes": 1, "manifest_sha256": "manifest-hash"},
        "analysis_sha256": "analysis-hash"}
    after = copy.deepcopy(before)
    after.update(observed_at="after")
    after["container"]["started_at"] = "start2"
    return before, after


def test_new_provider_rows_and_checkpoint_advance_are_allowed_while_old_rows_remain_equal():
    before, after = snapshots()
    after["database"]["events"]["2"] = "new-source-hash"
    after["database"]["checkpoints"]["public-channel"] = 124
    assert subject.compare(before, after)["status"] == "PASS"


@pytest.mark.parametrize("damage", ["not_restarted", "new_image", "lost_source", "edited_source", "lost_receipt",
    "regressed_checkpoint", "video_changed", "analysis_lost", "empty_baseline"])
def test_incomplete_or_changed_persistence_never_qualifies(damage):
    before, after = snapshots()
    if damage == "not_restarted":
        after["container"]["started_at"] = "start1"
    elif damage == "new_image":
        after["container"]["image"] = "changed-image"
    elif damage == "lost_source":
        after["database"]["events"].clear()
    elif damage == "edited_source":
        after["database"]["events"]["1"] = "changed source"
    elif damage == "lost_receipt":
        after["database"]["source_reports"].clear()
    elif damage == "regressed_checkpoint":
        after["database"]["checkpoints"]["public-channel"] = 122
    elif damage == "video_changed":
        after["video"]["sha256"] = "changed bytes"
    elif damage == "analysis_lost":
        after["analysis_sha256"] = "missing"
    else:
        before["database"]["events"].clear()
        before["database"]["source_reports"].clear()
    assert subject.compare(before, after)["status"] == "FAIL/INCOMPLETE"


def test_intentional_upgrade_requires_exact_declared_immutable_image_and_all_existing_bytes():
    before,after=snapshots()
    declared='sha256:'+'a'*64
    after['container']['image']=declared
    assert subject.compare(before,after)['status']=='FAIL/INCOMPLETE'
    qualified=subject.compare(before,after,expected_upgrade_image=declared)
    assert qualified['status']=='PASS'
    assert qualified['scope']=='coordinated_database_upgrade_existing_data_and_local_artifact_persistence'
    after['video']['sha256']='changed'
    assert subject.compare(before,after,expected_upgrade_image=declared)['status']=='FAIL/INCOMPLETE'


@pytest.mark.parametrize('declared',['mutable-tag','sha256:'+'b'*64])
def test_upgrade_option_does_not_admit_unqualified_or_different_image(declared):
    before,after=snapshots();after['container']['image']='sha256:'+'a'*64
    if declared=='mutable-tag':
        with pytest.raises(ValueError):subject.compare(before,after,expected_upgrade_image=declared)
    else:
        assert subject.compare(before,after,expected_upgrade_image=declared)['status']=='FAIL/INCOMPLETE'
