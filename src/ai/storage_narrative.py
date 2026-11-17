"""Narrative-only storage evidence and bounded correction. Never used by scoring."""
from contextvars import ContextVar
from copy import deepcopy
from datetime import date, timedelta
from functools import wraps
import inspect
import logging
import math
import re

log = logging.getLogger(__name__)
_scope = ContextVar("storage_narrative_scope", default=None)
_storage = re.compile(r"\bstorage\b|\binventor(?:y|ies)\b|\bunderground reserves\b", re.I)
_comparison = re.compile(
    r"(?:above|below|in line with|near|around|normal|surplus|deficit).{0,45}"
    r"(?:norm|average)|(?:norm|average).{0,45}(?:above|below)|"
    r"\bseasonal (?:buffer|adequacy)\b|"
    r"(?:5[- ]year|five[- ]year|seasonal)\s+(?:norm|average)|\bversus\b", re.I)
_adequate = re.compile(
    r"\b(?:comfort\w*|ampl(?!if)\w*|robust\w*|health\w*|"
    r"well[-\s]+(?:stock|pad|prepar|suppl)\w*|adequa\w*|sufficien\w*|"
    r"reassur\w*|plentiful\w*|abundan\w*|cushion\w*)\b|"
    r"\bsupportive\s+backdrop\s+for\s+storage\b|"
    r"\bhighly effective\b.{0,30}\brefill\b|\brefill\b.{0,60}\bhighly effective\b|"
    r"\breasonable seasonal buffer\b", re.I)
_scarce = re.compile(
    r"\b(?:tight\w*|deficit\w*|shortfall\w*)\b|"
    r"\bbelow[-\s]+(?:(?:seasonal|the)\s+)?(?:normal\w*|norm\w*|average\w*)", re.I)
_inactive = re.compile(
    r"(?:inactive|regional.spike|asset.risk).{0,180}"
    r"(?:means?|indicat\w*|reflect\w*|evidence|suggest\w*).{0,120}"
    r"(?:contain\w*|stabl\w*|resilien\w*|absen\w*|low risk)|"
    r"\breactivat\w*|\btemporarily inactive\b", re.I)


def as_day(value):
    return date.fromisoformat(str(value)[:10])


def context_from_row(row):
    """A norm is valid only for the preceding five complete years."""
    if not row:
        return None
    raw = row.get("raw_data") or {}
    if isinstance(raw, str):
        import json
        raw = json.loads(raw)
    gas_day = raw.get("gasDayStart") or raw.get("date")
    try:
        day = as_day(gas_day)
        fill = float(row["eu_storage_percent"])
        if not math.isfinite(fill):
            return None
    except (ValueError, TypeError, KeyError):
        return None
    result = {"row_id": row.get("id"), "physical_key": str(row["date"]),
              "gas_day": day.isoformat(), "fill_pct": fill, "verified": False}
    match = re.fullmatch(r"agsi_5y_(\d{4})_(\d{4})", row.get("norm_method") or "")
    if match and tuple(map(int, match.groups())) == (day.year - 5, day.year - 1):
        try:
            mean = float(row["seasonal_norm"])
            if math.isfinite(mean):
                result.update(verified=True, mean_pct=mean, deviation_pp=fill - mean,
                              years=f"{day.year-5}–{day.year-1}",
                              norm_method=row["norm_method"])
        except (ValueError, TypeError, KeyError):
            pass
    return result


def load_context(target, *, exact=False):
    """Legacy physical key is the index day, NOT the provider gas day."""
    from src.db.db import execute_one
    target = as_day(target)
    operator = "=" if exact else "<="
    row = execute_one(
        f"""SELECT id,date,eu_storage_percent,seasonal_norm,norm_method,raw_data
            FROM gas_storage_snapshots WHERE date {operator} %s
            ORDER BY date DESC LIMIT 1""", (target,))
    context = context_from_row(dict(row)) if row else None
    if context and as_day(context["gas_day"]) > target:
        return None
    return context


def sentence(context):
    if not context:
        return ""
    text = f"EU gas storage at {context['fill_pct']:.1f}%"
    if context.get("verified"):
        delta = context["deviation_pp"]
        if abs(delta) < .05:
            text += f", in line with the 5-year average ({context['years']})"
        else:
            text += (f", {abs(delta):.1f} pp {'below' if delta < 0 else 'above'} "
                     f"the 5-year average ({context['years']})")
    return text + f" as of gas day {context['gas_day']}."


def rules(context, methodology=False):
    result = (
        "\nSTORAGE EVIDENCE RULE: Use only the supplied as-of storage observation. "
        "Never use a 90% target as a seasonal norm. Do not infer storage adequacy "
        "from a low risk score. Neutral statements such as continued drawdown or "
        "conditional cold-weather withdrawals are allowed. "
    )
    if context and context.get("verified"):
        result += sentence(context) + (
            " Never state or imply the opposite direction. Beyond -5 pp, forbid "
            "all storage adequacy word stems: comfort*, ampl*, robust*, health*, "
            "well-stock*, well-pad*, well-prepar*, well-suppl*, adequa*, sufficien*, "
            "reassur*, plentiful, abundant, cushion*, supportive backdrop for storage, "
            "above seasonal norms/average and highly effective refill claims. "
            "Beyond +5 pp, forbid tight*, deficit*, shortfall* and below-normal/average "
            "storage claims. Neutral drawdown statements, negated adequacy claims and "
            "conditional weather-driven withdrawals remain allowed. Beyond either threshold never say "
            "'in line' with the average."
        )
    else:
        result += (
            "NO VERIFIED STORAGE REFERENCE: do not compare storage with any norm or "
            "average, and do not claim comfortable, ample, adequate, healthy, tight or "
            "deficit inventories. " + sentence(context))
    if methodology:
        from src.geri.narrative_context import INACTIVE_NOTE
        result += "\n" + INACTIVE_NOTE
    return result


_paragraph_break = re.compile(r"(\r?\n[ \t]*\r?\n(?:[ \t]*\r?\n)*)")
_sentence_break = re.compile(r"""[.!?](?:["'”’)])?(\s+)(?=[A-Z0-9*#\-\[])""")
_abbreviation = re.compile(
    r"(?:\b(?:[A-Za-z]\.){2,}|\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc)\.)$", re.I)


def _sentence_units(paragraph):
    """Return (sentence, original following whitespace), preserving offsets."""
    start = 0
    units = []
    for boundary in _sentence_break.finditer(paragraph):
        end = boundary.start(1)
        if _abbreviation.search(paragraph[:end]):
            continue
        units.append((paragraph[start:end], boundary.group(1)))
        start = boundary.end(1)
    units.append((paragraph[start:], ""))
    return units


def parts(text):
    return [body for paragraph in _paragraph_break.split(text or "")[::2]
            for body, _ in _sentence_units(paragraph) if body.strip()]


def _affirmed(pattern, text, *, hypothetical=False):
    """Negating a claim or describing a possible future drawdown is not adequacy."""
    for match in pattern.finditer(text):
        before, after = text[:match.start()], text[match.end():]
        if re.search(r"\b(?:not|never|no|without|cannot|can't)\s+(?!only\b)"
                     r"(?:(?!(?:but|and|or|yet|however)\b)[\w'-]+\s+){0,5}$", before, re.I):
            continue
        if re.match(r"\s+(?:cannot|can't|must not|should not|is not|are not)\s+"
                    r"(?:be\s+)?(?:infer|assum|establish|conclud|determin|claim|guarantee)\w*",
                    after, re.I):
            continue
        clause = re.split(r"[;.!?]|\bbut\b|\bhowever\b", before, flags=re.I)[-1]
        if hypothetical and re.search(r"\b(?:would|could|may|might|if|risk of)\b", clause, re.I):
            continue
        return True
    return False


def bad_sentence(text, context, methodology=False):
    if methodology and _inactive.search(text) and not re.search(
            r"\b(?:not|never|cannot|limitation)\b", text, re.I):
        return True
    if not _storage.search(text):
        return False
    if re.search(r"90\s*%.*(?:seasonal norm|seasonal average)|"
                 r"(?:seasonal norm|seasonal average).*90\s*%", text, re.I):
        return True
    if not context or not context.get("verified"):
        return bool(_affirmed(_comparison, text) or _affirmed(_adequate, text)
                    or _affirmed(_scarce, text, hypothetical=True))
    delta = context["deviation_pp"]
    if delta < 0 and _affirmed(re.compile(r"\babove\b.{0,35}(?:average|norm)", re.I), text):
        return True
    if delta > 0 and _affirmed(re.compile(r"\bbelow\b.{0,35}(?:average|norm)", re.I), text):
        return True
    if abs(delta) > 5 and re.search(r"\bin line\b", text, re.I):
        return True
    if delta < -5:
        return _affirmed(_adequate, text)
    if delta > 5:
        return _affirmed(_scarce, text, hypothetical=True)
    return False


def violations(text, context, methodology=False):
    return [p for p in parts(text) if bad_sentence(p, context, methodology)]


def sanitize(text, context, methodology=False):
    """Retain paragraph delimiters; append once in the first affected paragraph."""
    chunks = _paragraph_break.split(text or "")
    replacement = sentence(context)
    inserted = bool(replacement and replacement in (text or ""))
    changed = False
    for index in range(0, len(chunks), 2):
        units = _sentence_units(chunks[index])
        bad = [bad_sentence(body, context, methodology) for body, _ in units]
        if not any(bad):
            continue
        changed = True
        retained = "".join(body + space for (body, space), reject in zip(units, bad)
                           if not reject)
        if replacement and not inserted:
            retained = retained.rstrip(" \t\r\n") + (" " if retained.strip() else "") + replacement
            inserted = True
        else:
            retained = retained.rstrip(" \t\r\n")
        chunks[index] = retained
    if not changed:
        return text
    result = "".join(chunks)
    return result if result.strip() else ""


def completion(client, **kwargs):
    """One corrective retry per producer invocation, with rules on every attempt."""
    scope = _scope.get()
    if scope is None:
        return client.chat.completions.create(**kwargs)
    request = deepcopy(kwargs)
    constraint = rules(scope["context"], scope["methodology"])
    request["messages"] = [dict(m) for m in request["messages"]]
    request["messages"].insert(0, {"role": "system", "content": constraint})
    response = client.chat.completions.create(**request)
    scope["status"]["ai_section_missing"] = False
    text = response.choices[0].message.content or ""
    if violations(text, scope["context"], scope["methodology"]):
        if not scope["retried"]:
            scope["retried"] = True
            request["messages"] += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": "Correct the contradictory storage/methodology claims. "
                 + constraint}]
            try:
                response = client.chat.completions.create(**request)
            except Exception:
                scope["status"]["ai_section_missing"] = True
                raise
            text = response.choices[0].message.content or ""
        if violations(text, scope["context"], scope["methodology"]):
            scope["status"]["narrative_check_failed"] = True
            response.choices[0].message.content = sanitize(
                text, scope["context"], scope["methodology"]) or sentence(scope["context"]) or (
                    "No verified storage comparison is available.")
    return response


def terminal_fallback():
    scope = _scope.get()
    return bool(scope and scope["status"].get("narrative_check_failed"))


def producer(kind):
    """Keep status separate from string output; no global SDK monkeypatching."""
    def decorate(fn):
        signature = inspect.signature(fn)

        @wraps(fn)
        def guarded(*args, **kwargs):
            supplied_context = kwargs.pop("storage_narrative_context", None)
            status = kwargs.pop("narrative_status", None)
            status = status if status is not None else {}
            bound = signature.bind(*args, **kwargs)
            values = bound.arguments
            components = values.get("components")
            if kind == "geri" and components is None:
                return fn(*args, **kwargs)  # v1.1 remains byte-for-byte legacy behavior.
            target = values.get("index_date")
            if target is None:
                geri = values.get("geri")
                if isinstance(geri, list):
                    geri = geri[0] if geri else None
                target = (geri or {}).get("date") or (date.today() - timedelta(days=1))
            if supplied_context is None:
                try:
                    supplied_context = load_context(
                        target, exact=(kind == "egsi_s" or
                                       (kind == "egsi" and values.get("index_type") == "EGSI-S")))
                except Exception as exc:
                    log.warning("Narrative storage context unavailable (%s)", type(exc).__name__)
            methodology = kind == "geri"
            if kind in ("report", "delivery"):
                from src.geri.model_selection import published_model
                methodology = published_model() == "v1.2"
            status.setdefault("ai_section_missing", True)
            status.setdefault("narrative_check_failed", False)
            status["storage_context"] = supplied_context
            scope = {"context": supplied_context, "methodology": methodology,
                     "status": status, "retried": False}
            token = _scope.set(scope)
            try:
                result = fn(*args, **kwargs)
                if result is None:
                    status["ai_section_missing"] = True
                if isinstance(values.get("ai_status"), dict):
                    status["ai_section_missing"] = values["ai_status"].get(
                        "ai_section_missing", status["ai_section_missing"])
                # Includes deterministic/no-credentials and cached return paths.
                if isinstance(result, str):
                    result = sanitize(result, supplied_context, methodology)
                    if kind == "egsi" and status["ai_section_missing"] and sentence(supplied_context):
                        if sentence(supplied_context) not in result:
                            result += "\n" + sentence(supplied_context)
                return result
            finally:
                _scope.reset(token)
                if isinstance(components, dict):
                    components.update({k: status[k] for k in (
                        "ai_section_missing", "narrative_check_failed", "storage_context")})
                if isinstance(values.get("ai_status"), dict):
                    values["ai_status"].update(status)
        return guarded
    return decorate
