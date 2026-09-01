from pathlib import Path


WORKFLOWS = Path(".github/workflows")


def _workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _assert_direct_job(workflow_name: str, job_name: str) -> str:
    workflow = _workflow(workflow_name)

    assert "actions/checkout@v4.2.2" in workflow
    assert "actions/setup-python@v5.3.0" in workflow
    assert "pip install -r requirements.txt" in workflow
    assert (
        f"python scripts/replit_scheduled_job.py --job {job_name}" in workflow
    )
    assert "DATABASE_URL: ${{ secrets.DATABASE_URL }}" in workflow
    assert "INTERNAL_RUNNER_TOKEN: ${{ secrets.INTERNAL_RUNNER_TOKEN }}" in workflow
    assert "APP_URL:" not in workflow
    assert "curl " not in workflow
    return workflow


def test_alerts_workflow_runs_directly_with_manual_controls():
    workflow = _assert_direct_job("alerts_engine_v2.yml", "alerts")

    assert "cron: '*/10 * * * *'" in workflow
    assert "timeout-minutes: 30" in workflow
    assert "group: alerts-engine-v2" not in workflow
    assert "PHASE: ${{ github.event.inputs.phase || 'all' }}" in workflow
    assert "DRY_RUN: ${{ github.event.inputs.dry_run || 'false' }}" in workflow
    assert "ALERTS_ENABLED: ${{ github.event.inputs.alerts_enabled || 'true' }}" in workflow
    assert (
        "INCLUDE_PRO_DELIVERY: "
        "${{ github.event.inputs.include_pro_delivery || 'true' }}"
    ) in workflow
    assert (
        "INCLUDE_TRADER_DELIVERY: "
        "${{ github.event.inputs.include_trader_delivery || 'true' }}"
    ) in workflow


def test_auxiliary_captures_cannot_block_alert_delivery():
    workflow = _workflow("alerts_engine_v2.yml")

    for job_name in ("metadata", "intraday", "ingestion", "daily"):
        assert f"--job {job_name}" not in workflow


def test_intraday_capture_has_independent_direct_schedule():
    workflow = _assert_direct_job("intraday-market-data.yml", "intraday")

    assert "cron: '*/10 * * * *'" in workflow
    assert "timeout-minutes: 7" in workflow
    assert "group: intraday-market-data" not in workflow


def test_daily_workflow_uses_one_direct_locked_pipeline():
    workflow = _assert_direct_job("geri-daily.yml", "daily")

    assert "cron: '30 1 * * *'" in workflow
    assert "timeout-minutes: 40" in workflow
    assert (
        "OIL_PRICE_API_KEY: "
        "${{ secrets.OIL_PRICE_API_KEY || secrets.OILPRICE_API_KEY }}"
    ) in workflow
    assert "Validate daily data-source configuration" in workflow
    assert "group: daily-index-computation" not in workflow
    assert (
        "INCLUDE_DELIVERY: "
        "${{ github.event.inputs.include_delivery || 'true' }}"
    ) in workflow


def test_ingestion_pipeline_uses_one_direct_locked_operation():
    workflow = _assert_direct_job("ingestion_pipeline.yml", "ingestion")

    assert "cron: '0 * * * *'" in workflow
    assert "timeout-minutes: 28" in workflow
    assert "group: ingestion-pipeline" not in workflow
    assert "SKIP_AI: ${{ github.event.inputs.skip_ai || 'false' }}" in workflow
    assert "SKIP_RISK: ${{ github.event.inputs.skip_risk || 'false' }}" in workflow


def test_metadata_backfill_runs_directly_and_preserves_dry_run():
    workflow = _assert_direct_job("alert-metadata-backfill.yml", "metadata")

    assert "cron: '16 * * * *'" in workflow
    assert "timeout-minutes: 10" in workflow
    assert "DRY_RUN: ${{ github.event.inputs.dry_run || 'false' }}" in workflow


def test_dispatch_inputs_are_not_interpolated_in_summary_shell():
    for workflow_name in (
        "alerts_engine_v2.yml",
        "ingestion_pipeline.yml",
        "alert-metadata-backfill.yml",
        "geri-daily.yml",
    ):
        summary = _workflow(workflow_name).split("- name: Summary", 1)[1]
        assert "${{ github.event.inputs." not in summary