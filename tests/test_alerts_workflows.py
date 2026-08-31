from pathlib import Path
import re


WORKFLOWS = Path(".github/workflows")


def _workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_alerts_workflow_uses_application_lock_instead_of_actions_queue():
    workflow = _workflow("alerts_engine_v2.yml")

    assert "cron: '*/10 * * * *'" in workflow
    assert "group: alerts-engine-v2" not in workflow
    assert "/internal/run/alerts" in workflow
    assert "timeout-minutes: 13" in workflow
    assert "--connect-timeout 10 --max-time 480" in workflow
    assert "Verify required steps" in workflow
    assert "--data-urlencode" in workflow
    assert "PHASE: ${{ github.event.inputs.phase || 'all' }}" in workflow
    assert "ALERTS_ENABLED: ${{ github.event.inputs.alerts_enabled || 'true' }}" in workflow


def test_alert_job_deadline_exceeds_all_required_http_budgets():
    workflow = _workflow("alerts_engine_v2.yml")
    job_timeout = int(re.search(r"timeout-minutes: (\d+)", workflow).group(1))
    request_timeouts = [
        int(value) for value in re.findall(r"--max-time (\d+)", workflow)
    ]

    assert request_timeouts == [480, 90, 90]
    assert job_timeout * 60 >= sum(request_timeouts) + 120


def test_auxiliary_captures_cannot_block_alert_delivery():
    workflow = _workflow("alerts_engine_v2.yml")

    for endpoint in (
        "/internal/run/gas-storage-capture",
        "/internal/run/egsi-compute",
        "/internal/run/egsi-s-compute",
        "/internal/run/oil-price-capture",
        "/internal/run/intraday-price-capture",
    ):
        assert endpoint not in workflow


def test_intraday_capture_has_independent_bounded_schedule():
    workflow = _workflow("intraday-market-data.yml")

    assert "cron: '*/10 * * * *'" in workflow
    assert "group: intraday-market-data" in workflow
    assert "timeout-minutes: 7" in workflow
    assert "/internal/run/intraday-price-capture" in workflow
    assert "--connect-timeout 10 --max-time 60" in workflow
    assert "--retry 2" in workflow
    assert '--retry-max-time 180' in workflow
    assert 'if [ "$http_code" = "409" ]' in workflow


def test_daily_workflow_owns_daily_captures_with_bounded_requests():
    workflow = _workflow("geri-daily.yml")

    oil = workflow.index("/internal/run/oil-price-capture")
    geri = workflow.index("/internal/run/geri-compute")
    storage = workflow.index("/internal/run/gas-storage-capture")
    egsi_system = workflow.index("/internal/run/egsi-s-compute")

    assert oil < geri
    assert storage < egsi_system
    assert "group: daily-index-computation" in workflow
    assert "timeout-minutes: 40" in workflow

    curl_lines = [line for line in workflow.splitlines() if "response=$(curl" in line]
    assert curl_lines
    assert all("--connect-timeout 10" in line for line in curl_lines)
    assert all("-m 180" in line for line in curl_lines)


def test_delivery_posts_are_not_retried_after_unknown_provider_outcome():
    workflow = _workflow("alerts_engine_v2.yml")

    assert "--retry" not in workflow
    assert "/internal/run/pro-delivery?since_minutes=15&include_geri=true" in workflow
    assert "/internal/run/trader-delivery?since_minutes=30" in workflow
    assert "pro_delivery_missing" in workflow
    assert "trader_delivery_missing" in workflow


def test_dispatch_inputs_are_not_interpolated_in_summary_shell():
    workflow = _workflow("alerts_engine_v2.yml")
    summary = workflow.split("- name: Summary", 1)[1]

    assert "${{ github.event.inputs.phase" not in summary
    assert "${{ github.event.inputs.dry_run" not in summary
    assert 'printf \'| Phase | %s |\\n\' "$PHASE"' in summary
