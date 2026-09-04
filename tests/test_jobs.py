from pathlib import Path

import pytest

from api.jobs import JobStore


def make_store(tmp_path: Path):
    return JobStore(str(tmp_path / "jobs.sqlite3"))


def test_put_get_and_public_dict(tmp_path):
    store = make_store(tmp_path)
    job = store.put(
        job_id="ana_test123",
        provider="runpod",
        provider_job_id="provider-secret-id",
        status="submitted",
        cost_estimate={"ready": True, "estimated_cost_usd": 0.12},
        request_summary={"video_duration_seconds": 120},
    )

    loaded = store.get("ana_test123")
    assert loaded.provider_job_id == "provider-secret-id"
    assert loaded.status == "submitted"
    assert loaded.cost_estimate["estimated_cost_usd"] == 0.12

    public = store.public_dict(job)
    assert public["job_id"] == "ana_test123"
    assert "provider_job_id" not in public


def test_list_recent_is_newest_first(tmp_path):
    store = make_store(tmp_path)
    store.put(
        job_id="ana_one",
        provider="runpod",
        provider_job_id="r1",
        status="submitted",
        cost_estimate={},
        request_summary={},
    )
    store.put(
        job_id="ana_two",
        provider="runpod",
        provider_job_id="r2",
        status="submitted",
        cost_estimate={},
        request_summary={},
    )

    jobs = store.list_recent()
    assert [job.job_id for job in jobs][:2] == ["ana_two", "ana_one"]


def test_update_status(tmp_path):
    store = make_store(tmp_path)
    store.put(
        job_id="ana_status",
        provider="runpod",
        provider_job_id="r3",
        status="submitted",
        cost_estimate={},
        request_summary={},
    )

    updated = store.update_status("ana_status", "completed")
    assert updated.status == "completed"
    assert updated.updated_at >= updated.created_at


def test_unknown_job_raises_key_error(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(KeyError):
        store.get("missing")
