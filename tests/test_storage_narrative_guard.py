"""Offline narrative regressions. Root conftest blocks production DB and HTTP."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from src.ai.storage_narrative import (
    completion, context_from_row, producer, sanitize, sentence, violations, load_context,
)
from src.ai.repair_storage_narratives import repaired_payload


def context(fill=70.39, mean=88.36, method="agsi_5y_2021_2025"):
    return context_from_row({"id": 8080, "date": date(2026, 11, 16),
                             "eu_storage_percent": fill, "seasonal_norm": mean,
                             "norm_method": method, "raw_data": {"gasDayStart": "2026-11-15"}})


BAD = [
    "Storage stress remains minimal, indicating that the region’s underground inventories are well above seasonal norms.",
    "For utilities and industrial buyers, this translates to a reassuring backdrop: storage levels remain comfortably above seasonal norms, ensuring that withdrawal rates can be managed without triggering price spikes or supply concerns.",
    "Storage levels, while not at historic highs, are comfortably adequate for this point in the withdrawal season.",
    "Current infrastructure capacity and storage levels provide a comfortable operational buffer for market participants.",
    "EU storage inventories are ample.",
    "EU storage remains robust.",
    "Storage levels are healthy.",
    "Storage facilities are well-stocked.",
    "Storage inventories remain well-padded.",
    "EU storage is well-prepared for winter.",
    "Storage provides an adequate buffer.",
    "Highly effective refill has kept storage ready for winter.",
]


@pytest.mark.parametrize("text", BAD)
def test_exact_incidents_and_adequacy(text):
    assert violations(text, context())
    assert not violations(sanitize(text, context()), context())


@pytest.mark.parametrize("text", [
    "Storage continues to draw down.",
    "A cold spell would accelerate storage withdrawals.",
    "A disruption could tighten storage balances.",
    "EU gas storage at 70.4%, 18.0 pp below the 5-year average (2021–2025).",
    "Ample LNG deliveries are supporting imports.",
])
def test_neutral_and_correct_negative(text):
    assert not violations(text, context())


@pytest.mark.parametrize("text", [
    "Storage is below normal.", "Storage inventories are tight.",
    "EU storage has a deficit.", "Storage is in line with the average.",
])
def test_positive_mirror(text):
    assert violations(text, context(95, 80))


@pytest.mark.parametrize("method", [None, "monthly", "agsi_5y_2020_2024"])
def test_no_unverified_reference(method):
    c = context(method=method)
    assert not c["verified"]
    assert "average" not in sentence(c)
    assert violations("Storage is above average.", c)
    assert not violations("Storage continues to draw down.", c)


def test_gas_day_required_and_reference_year_rollover():
    assert context_from_row({"date": "2026-11-16", "eu_storage_percent": 70}) is None
    c = context_from_row({"date": "2027-01-02", "eu_storage_percent": 70,
                          "seasonal_norm": 80, "norm_method": "agsi_5y_2022_2026",
                          "raw_data": {"gasDayStart": "2027-01-01"}})
    assert c["years"] == "2022–2026"


def test_query_is_asof_and_exact_for_egsi(monkeypatch):
    import src.db.db as db
    read = Mock(return_value=None)
    monkeypatch.setattr(db, "execute_one", read)
    load_context("2026-11-16")
    assert "date <=" in read.call_args.args[0]
    load_context("2026-11-16", exact=True)
    assert "date =" in read.call_args.args[0]
    assert read.call_args.args[1] == (date(2026, 11, 16),)


def response(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


@pytest.mark.parametrize("second_good", [True, False])
def test_retry_then_preserve_ai_flag_and_fallback(second_good):
    good = sentence(context())
    create = Mock(side_effect=[response(BAD[1]), response(good if second_good else BAD[0])])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    @producer("egsi")
    def generate(index_date, components):
        return completion(client, messages=[{"role": "user", "content": "Write."}]).choices[0].message.content
    status = {}
    result = generate("2026-11-16", {}, storage_narrative_context=context(), narrative_status=status)
    assert create.call_count == 2
    assert status["ai_section_missing"] is False
    assert status["narrative_check_failed"] is (not second_good)
    assert not violations(result, context())
    for call in create.call_args_list:
        assert any(m["role"] == "system" and "STORAGE EVIDENCE" in m["content"]
                   for m in call.kwargs["messages"])


def test_no_ai_fallback_is_checked():
    @producer("egsi")
    def generate(index_date):
        return BAD[3]
    status = {}
    result = generate("2026-11-16", storage_narrative_context=context(), narrative_status=status)
    assert status["ai_section_missing"] is True
    assert status["narrative_check_failed"] is False
    assert "comfortable" not in result


def test_geri_inactive_status_regression_and_v11_passthrough():
    text = "The inactive status of regional and asset-specific risk components means that volatility is contained."
    assert violations(text, context(), True)
    @producer("geri")
    def generate(index_date, components=None):
        return text
    assert generate("2026-11-16") == text
    assert generate("2026-11-16", {}, storage_narrative_context=context()) != text


def test_repair_changes_only_narrative_leaves():
    old = {"id": 7, "value": 4, "computed_at": "unchanged", "interpretation": BAD[0],
           "components": {"score": 19, "interpretation": BAD[0],
                          "ai_section_missing": False, "narrative_check_failed": False}}
    new = repaired_payload(old, context())
    assert old["interpretation"] == BAD[0]
    assert new["value"] == old["value"] and new["computed_at"] == old["computed_at"]
    assert new["components"]["score"] == 19
    assert new["components"]["narrative_check_failed"] is False
    assert new["components"]["ai_section_missing"] is False


def module_at(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("repository", ["website", "ops"])
@pytest.mark.parametrize("kind", ["geri", "egsi", "report", "delivery"])
@pytest.mark.parametrize("recovered", [False, True])
def test_real_producers(repository, kind, recovered, monkeypatch):
    """Run the actual changed producer functions, not only the shared helper."""
    from pathlib import Path
    import sys
    import openai
    root = Path(__file__).resolve().parents[1]
    ops = root / "generated-artifacts/narrative-phase-b-ops"
    if repository == "ops" and not ops.exists():
        pytest.skip("Ops overlay is not part of website checkout")
    if repository == "ops":
        for name, file in [
            ("src.ai.interpretation_client", "src/ai/interpretation_client.py"),
            ("src.geri.delivery_context", "src/geri/delivery_context.py")]:
            monkeypatch.setitem(sys.modules, name, module_at(ops / file, "offline_helper"))
    files = {"geri": "src/geri/interpretation.py", "egsi": "src/egsi/interpretation.py",
             "report": "src/api/daily_digest_routes.py",
             "delivery": "src/delivery/pro_delivery_worker.py"}
    module = module_at((ops if repository == "ops" else root) / files[kind],
                       f"offline_{repository}_{kind}")
    monkeypatch.setenv("OPENAI_API_KEY", "offline")
    monkeypatch.setattr(module, "AI_INTEGRATIONS_OPENAI_API_KEY", "offline", raising=False)
    monkeypatch.setattr(module, "AI_INTEGRATIONS_OPENAI_BASE_URL", "https://offline.invalid", raising=False)
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", "v1.2")
    good = ("Monitor the dated observations and event evidence without inferring unmeasured conditions. " * 20
            + "\n\n" + sentence(context()))
    create = Mock(side_effect=[response(BAD[1]), response(good if recovered else BAD[0])])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(openai, "OpenAI", Mock(return_value=client))
    status = {}
    kw = {"storage_narrative_context": context(), "narrative_status": status}
    if kind == "geri":
        result = module.generate_interpretation(4, "LOW", [], [], "2026-11-16", components={}, **kw)
    elif kind == "egsi":
        result = module.generate_egsi_interpretation(1, "LOW", [], {}, "2026-11-16",
                                                    index_type="EGSI-S", **kw)
    elif kind == "report":
        result = module.generate_ai_digest("enterprise", [], [{"date": "2026-11-16", "value": 4}],
                                           [], [], {}, None, None, {"tone": "Calm"}, "Calm", **kw)
    else:
        result = module.generate_ai_digest_for_plan(
            "free", {"date": "2026-11-16", "value": 4}, None, {}, **kw)
    assert result
    assert create.call_count == 2
    assert not violations(result, context())
    assert status["narrative_check_failed"] is (not recovered)
    assert status["ai_section_missing"] is False


def test_latest_repair_dry_run_and_wrong_target_guard():
    from src.ai.repair_storage_narratives import main
    import sys
    from unittest.mock import patch
    with patch.object(sys, "argv", ["repair", "--production"]):
        with pytest.raises(SystemExit):
            main()


def test_repair_dry_run_selects_only_latest_v12_day_and_never_writes():
    from src.ai.repair_storage_narratives import run
    from contextlib import nullcontext
    day = date(2026, 11, 16)
    storage = {"id": 8080, "date": day, "eu_storage_percent": 70.39,
               "seasonal_norm": 88.36, "norm_method": "agsi_5y_2021_2025",
               "raw_data": {"gasDayStart": "2026-11-15"}}
    index = {"id": 1, "value": 4, "interpretation": BAD[0]}
    cache = {"cache_key": "v1:4:2026-11-16:l:geri_v1.2", "narrative": BAD[0]}
    cur = Mock()
    cur.fetchone.side_effect = [{"day": day}, {"day": day}, storage,
                                {"day": day}, storage, {"day": day}, storage, storage]
    cur.fetchall.side_effect = [[index], [index], [index], [cache]]
    conn = Mock()
    conn.cursor.return_value = nullcontext(cur)
    report = run(conn)
    assert report["index_day"] == "2026-11-16" and report["apply"] is False
    assert len(report["changes"]) == 4
    sql = "\n".join(c.args[0] for c in cur.execute.call_args_list)
    assert "UPDATE " not in sql and "DELETE " not in sql
    assert "index_id='global:geo_energy_risk'" in sql and ":geri_v1.2" in sql


def test_delivery_and_report_storage_queries_are_pinned(monkeypatch):
    from src.delivery import pro_delivery_worker as delivery
    from src.api import daily_digest_routes as report
    read_delivery, read_report = Mock(return_value=None), Mock(return_value=[])
    monkeypatch.setattr(delivery, "execute_one", read_delivery)
    monkeypatch.setattr(report, "execute_production_query", read_report)
    delivery.get_asset_snapshots(target_date=date(2026, 11, 16))
    sql, params = read_delivery.call_args.args
    assert "WHERE date <=" in sql and params == (date(2026, 11, 16),)
    assert all(column in sql for column in ("norm_method", "seasonal_norm", "raw_data"))
    report.get_asset_snapshots(target_date=date(2026, 11, 16))
    sql, params = read_report.call_args.args
    assert "WHERE date <=" in sql and params[0] == date(2026, 11, 16)


def test_deterministic_takeaway_contains_no_threshold_adequacy():
    from src.api.daily_digest_routes import build_actionable_takeaways
    result = build_actionable_takeaways([], [], [], {}, [], "Calm", 70.39, 10, 20)
    assert "reasonable seasonal buffer" not in str(result)


@pytest.mark.parametrize("module_path", ["src/geri/interpretation.py",
    "generated-artifacts/narrative-phase-b-ops/src/geri/interpretation.py"])
def test_actual_v11_generator_keeps_original_prompt_and_does_not_read_storage(module_path, monkeypatch):
    from pathlib import Path
    import sys
    import openai
    import src.ai.storage_narrative as guard
    root = Path(__file__).resolve().parents[1]
    if not (root / module_path).exists():
        pytest.skip("Ops overlay not checked out")
    if "generated-artifacts" in module_path:
        monkeypatch.setitem(sys.modules, "src.ai.interpretation_client",
            module_at(root / "generated-artifacts/narrative-phase-b-ops/src/ai/interpretation_client.py",
                      "offline_client"))
    module = module_at(root / module_path, "offline_v11")
    monkeypatch.setenv("OPENAI_API_KEY", "offline")
    monkeypatch.setattr(module, "AI_INTEGRATIONS_OPENAI_API_KEY", "offline", raising=False)
    monkeypatch.setattr(module, "AI_INTEGRATIONS_OPENAI_BASE_URL", "https://offline.invalid", raising=False)
    read = Mock(side_effect=AssertionError("v1.1 must not read storage"))
    monkeypatch.setattr(guard, "load_context", read)
    text = "Legacy interpretation remains unchanged. " * 60 + "\n\nLegacy second paragraph."
    create = Mock(return_value=response(text))
    monkeypatch.setattr(openai, "OpenAI", Mock(return_value=SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))))
    module.generate_interpretation(10, "LOW", [], [], "2026-11-16")
    assert not read.called
    assert "STORAGE EVIDENCE" not in str(create.call_args)
