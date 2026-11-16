"""No provider calls: capture prompts for v1.2 and the unchanged v1.1 path."""
import copy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def modules(monkeypatch):
    base=Path(__file__).resolve().parents[1]/"src"/"geri"
    def load(name, filename):
        spec=importlib.util.spec_from_file_location(name,base/filename)
        module=importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,name,module)
        spec.loader.exec_module(module)
        return module
    context=load("src.geri.narrative_context","narrative_context.py")
    helper=ModuleType("src.ai.interpretation_client")
    helper.client_options=lambda:({"api_key":"offline"},"direct")
    helper.record_status=lambda *a,**kw:None
    monkeypatch.setitem(sys.modules,helper.__name__,helper)
    generator=load("offline_geri_interpretation","interpretation.py")
    return context,generator


def test_v12_context_omits_inactive_numeric_components_without_mutating_inputs(modules):
    context,_=modules
    components={"weights":{"regional_spike":.25},"asset_risk_score":10,
                "regional_spike_score":20,"high_impact_score":30,"top_drivers":[]}
    before=copy.deepcopy(components)
    result=context.interpretation_context(components)
    assert result["component_status"]["asset_risk"]=="inactive_methodology_component"
    assert result["components"]=={"high_impact_score":30,"top_drivers":[]}
    assert components==before


@pytest.mark.parametrize("v12",[False,True])
def test_system_prompt_and_length_retry_preserve_version_rules(modules,monkeypatch,v12):
    context,generator=modules
    calls=[]
    def create(**kw):
        calls.append(copy.deepcopy(kw))
        text="too short" if len(calls)==1 else (" ".join(["evidence"]*110)+"\n\n")*2
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    import openai
    monkeypatch.setattr(openai,"OpenAI",lambda **kw:SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    generator.generate_interpretation(7,"LOW",[],[],"2026-11-14",
                                     components={"high_impact_score":30} if v12 else None)
    assert len(calls)==2
    if v12:
        assert context.INACTIVE_NOTE in calls[0]["messages"][0]["content"]
        assert context.INACTIVE_NOTE in calls[1]["messages"][-1]["content"]
        assert "inactive_methodology_component" in calls[0]["messages"][1]["content"]
    else:
        assert "inactive_methodology_component" not in str(calls)
        assert context.INACTIVE_NOTE not in str(calls)
        assert calls[1]["messages"][-1]["content"] == (
            "This is too brief. Please expand to 2-3 full paragraphs with 250-400 words total. "
            "Provide more detailed analysis of the drivers and forward-looking context.")


def test_v11_context_contract_unchanged(modules):
    context,_=modules
    components={"asset_risk_score":10,"weights":{"asset_risk":.2}}
    assert context.interpretation_context(components,version="v1.1")=={
        "methodology_version":"v1.1","model_version":"geri_v1.1",
        "inactive_component_note":None,"components":components}
