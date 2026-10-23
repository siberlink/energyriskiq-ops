"""Explicit methodology switches; unsupported changes fail rather than do nothing."""
from dataclasses import asdict, dataclass, replace
import math
import re


@dataclass(frozen=True)
class GeriVariant:
    name: str = "baseline"
    accepted_types: tuple = (
        "HIGH_IMPACT_EVENT", "REGIONAL_RISK_SPIKE", "ASSET_RISK_ALERT"
    )
    risk_score_source: str = "confidence"
    min_confidence: float | None = None
    require_geri_driver: bool = False
    relevance_filter: str = "none"
    relevance_rule: str = "none"
    label_model: str = "mini"
    pillar_mode: str = "none"
    dedup_mode: str = "none"
    carryover_half_life_days: float | None = None
    weekday_adjust: bool = False
    scaling: str = "minmax_90d"
    baseline_window_days: int = 90
    min_history_rows: int = 14
    degraded_alert_floor: float | None = None
    display_smoothing: tuple | None = None
    weights: tuple = (0.40, 0.25, 0.20, 0.15)

    def validate(self):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", self.name):
            raise ValueError("Variant name must be a safe directory name.")
        if not isinstance(self.baseline_window_days, int) or self.baseline_window_days < 1:
            raise ValueError("baseline_window_days must be a positive integer.")
        if self.min_confidence is not None and not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be between zero and one.")
        if self.relevance_filter not in ("none", "cheap", "llm"):
            raise ValueError("Unknown relevance_filter.")
        if self.relevance_rule not in ("none", "r_current", "r_material", "r_material_events", "r_high"):
            raise ValueError("Unknown relevance_rule.")
        if self.label_model not in ("mini", "gpt41"):
            raise ValueError("Unknown label_model.")
        if self.pillar_mode not in ("none", "fixed_alerts", "fixed_alerts_sev4", "continuous",
                                    "timely_continuous", "timely_alerts"):
            raise ValueError("Unknown pillar_mode.")
        if self.dedup_mode not in ("none", "storyline_day", "storyline_day_corroborated",
                                   "storyline_day_damp_log"):
            raise NotImplementedError("Unknown dedup_mode.")
        if self.carryover_half_life_days is not None and (
                not math.isfinite(self.carryover_half_life_days) or self.carryover_half_life_days<=0):
            raise ValueError("Carry-over half-life must be positive and finite.")
        if not isinstance(self.weekday_adjust,bool):
            raise ValueError("weekday_adjust must be boolean.")
        if self.display_smoothing is not None and (
                len(self.display_smoothing)!=2 or self.display_smoothing[0]!="fast_up_slow_down"
                or not math.isfinite(self.display_smoothing[1]) or self.display_smoothing[1]<=0):
            raise ValueError("Display smoothing requires ('fast_up_slow_down', positive half-life).")
        defaults = asdict(GeriVariant())
        for key, value in asdict(self).items():
            if key == "degraded_alert_floor" and value not in (None, 0.40):
                raise NotImplementedError("Only the integrity_v1 0.40 health floor is supported.")
            if key not in ("name", "baseline_window_days", "degraded_alert_floor",
                           "min_confidence", "require_geri_driver", "relevance_filter",
                           "relevance_rule", "dedup_mode", "label_model", "pillar_mode",
                           "carryover_half_life_days","weekday_adjust","display_smoothing") and value != defaults[key]:
                raise NotImplementedError(f"Switch {key!r} is reserved for a later step.")
        return self


BASELINE = GeriVariant()
VARIANTS = {
    "baseline": BASELINE,
    "baseline_91": replace(BASELINE, name="baseline_91", baseline_window_days=91),
    "integrity_v1": replace(BASELINE, name="integrity_v1", degraded_alert_floor=0.40),
    "relevance_cheap": replace(BASELINE, name="relevance_cheap", degraded_alert_floor=0.40,
                             relevance_filter="cheap"),
    "relevance_llm": replace(BASELINE, name="relevance_llm", degraded_alert_floor=0.40,
                           relevance_filter="llm"),
}
for name, rule, dedup in (
    ("dedup_only", "none", "storyline_day"),
    ("dedup_corr", "none", "storyline_day_corroborated"),
    ("rel_dedup", "r_material_events", "storyline_day_corroborated"),
    ("relhigh_dedup", "r_high", "storyline_day_corroborated"),
    ("rel_only", "r_material_events", "none"),
):
    VARIANTS[name] = replace(VARIANTS["integrity_v1"], name=name,
                             relevance_rule=rule, dedup_mode=dedup)
for name, pillar, model, rule, dedup in (
    ("rel41_only", "none", "gpt41", "r_material_events", "none"),
    ("pillars_fixed_alerts", "fixed_alerts", "mini", "none", "none"),
    ("pillars_fixed_alerts_sev4", "fixed_alerts_sev4", "mini", "none", "none"),
    ("pillars_continuous", "continuous", "mini", "none", "none"),
    ("pillars_continuous_rel41", "continuous", "gpt41", "r_material_events", "none"),
    ("damp_log", "none", "mini", "none", "storyline_day_damp_log"),
):
    VARIANTS[name] = replace(VARIANTS["integrity_v1"], name=name, pillar_mode=pillar,
                             label_model=model, relevance_rule=rule, dedup_mode=dedup)
for name, mode, model, rule in (
    ("pillars_continuous_timely", "timely_continuous", "mini", "none"),
    ("pillars_alerts_timely", "timely_alerts", "mini", "none"),
    ("pillars_continuous_timely_rel41", "timely_continuous", "gpt41", "r_material_events"),
):
    VARIANTS[name] = replace(VARIANTS["integrity_v1"], name=name, pillar_mode=mode,
                             label_model=model, relevance_rule=rule)

for name,changes in {
    "carry15":{"carryover_half_life_days":1.5},
    "carry25":{"carryover_half_life_days":2.5},
    "wk":{"weekday_adjust":True},
    "wk_carry15":{"weekday_adjust":True,"carryover_half_life_days":1.5},
    "wk_carry15_rel41":{"weekday_adjust":True,"carryover_half_life_days":1.5,
                        "label_model":"gpt41","relevance_rule":"r_material_events"},
    "wk_carry15_mm180":{"weekday_adjust":True,"carryover_half_life_days":1.5,
                        "baseline_window_days":180},
    "fusd2":{"display_smoothing":("fast_up_slow_down",2.)},
    "wk_carry15_pillars_v2_rel41":{"weekday_adjust":True,"carryover_half_life_days":1.5,
                        "label_model":"gpt41","relevance_rule":"r_material_events",
                        "pillar_mode":"continuous"},
}.items():
    VARIANTS[name]=replace(VARIANTS["integrity_v1"],name=name,**changes)


def get_variant(name):
    if name not in VARIANTS:
        raise ValueError(f"Unknown variant {name!r}; available: {', '.join(VARIANTS)}")
    return VARIANTS[name].validate()
