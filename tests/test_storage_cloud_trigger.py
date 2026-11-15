from unittest.mock import Mock

import pytest

from src.storage import cloud_trigger


def test_cloud_calls_website_only_no_local_storage_or_redirects(monkeypatch):
    monkeypatch.setenv("WEBSITE_BASE_URL","https://example.invalid")
    monkeypatch.setenv("CLOUD_RUN_EXECUTION","offline")
    response=Mock(status_code=200)
    response.json.return_value={"status":"ok","details":{"status":"success","observations":77}}
    post=Mock(return_value=response)
    monkeypatch.setattr(cloud_trigger.requests,"post",post)
    result=cloud_trigger.run_website_storage("offline-token","2026-11-14")
    assert result["observations"]==77
    assert post.call_args.args[0]=="https://example.invalid/internal/run/storage-pipeline"
    assert post.call_args.kwargs["allow_redirects"] is False
    assert post.call_args.kwargs["headers"]["X-Cloud-Execution"]=="offline"


@pytest.mark.parametrize("status",[302,409,500,524])
def test_failure_is_explicit_never_local_fallback(monkeypatch,status):
    monkeypatch.setenv("WEBSITE_BASE_URL","https://example.invalid")
    post=Mock(return_value=Mock(status_code=status))
    monkeypatch.setattr(cloud_trigger.requests,"post",post)
    with pytest.raises(RuntimeError,match="HTTP"):
        cloud_trigger.run_website_storage("offline")
    assert post.call_count==1


def test_auth_and_complete_snapshot_required(monkeypatch):
    monkeypatch.setenv("WEBSITE_BASE_URL","https://example.invalid")
    with pytest.raises(ValueError,match="authentication"):
        cloud_trigger.run_website_storage()
    response=Mock(status_code=200)
    response.json.return_value={"status":"ok","details":{"status":"success","observations":76}}
    monkeypatch.setattr(cloud_trigger.requests,"post",Mock(return_value=response))
    with pytest.raises(RuntimeError,match="incomplete"):
        cloud_trigger.run_website_storage("offline")
