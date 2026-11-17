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
_storage = re.compile(r"\bstorage\b|\binventor(?:y|ies)\b|\bstocks?\b|\bunderground reserves\b", re.I)
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
_storage_assurance = re.compile(
    r"\b(?:resilien\w*|mitigat\w*)\b|"
    r"\b(?:stable|steady)\s+(?:\w+\s+){0,4}(?:storage|inventor(?:y|ies)|stocks?)\b|"
    r"\b(?:storage|inventor(?:y|ies)|stocks?)\s*[:*-]*\s*"
    r"(?:(?:levels?|is|are|remain\w*)\s+){0,3}(?:stability|stable|steady)\b|"
    r"\bnear[-\s]+steady\b|\bbuffer\s+capacity\s+mitigat\w*\b|"
    r"\bprovid\w*\s+(?:an?\s+)?buffer\b", re.I)
_components = re.compile(r"\bcomponent\w*\b|\bregional[-_\s]+spike\b|\basset[-_\s]+risk\b", re.I)
_inactive_status = re.compile(r"\binactiv\w*\b|\bregional[-_\s]+spike\b|\basset[-_\s]+risk\b", re.I)
_market_state = re.compile(
    r"\b(?:contain\w*|stabl\w*|muted|low|calm|resilien\w*)\b|"
    r"\b(?:no|without|absent)\s+spillover\b", re.I)
_causal = re.compile(
    r"\b(?:mean\w*|indicat\w*|reflect\w*|evidence|suggest\w*|signal\w*|show\w*|"
    r"impl(?:y|i\w*)|demonstrat\w*|confirm\w*|explain\w*|ensur\w*|"
    r"support\w*|keep\w*|kept|leav\w*|left|lead\w*|led|result\w*|"
    r"contribut\w*|prevent\w*|underpin\w*|attribut\w*|because|therefore|hence|thus|given)\b|"
    r"\bdue\s+to\b|\bsigns?\s+of\b|\bconsistent\s+with\b", re.I)
_reactivation = re.compile(r"\breactivat\w*|\btemporarily inactive\b", re.I)
_component_state = re.compile(
    r"\b(?:components?|status)\s+(?:is|are|remain\w*)\s+"
    r"(?:contained|stable|muted|low|calm|resilient)\b", re.I)


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
            "resilien*, mitigat*, stable/steady storage, storage stability, near steady, "
            "supported by stable storage, buffer capacity mitigates, provides a buffer, "
            "above seasonal norms/average and highly effective refill claims. "
            "Apply these only to sentences mentioning storage, inventories or stocks. "
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
        result += ("\n" + INACTIVE_NOTE +
                   " Remove any sentence linking inactive regional/asset components to "
                   "contained, stable, muted, low, calm or resilient markets, no spillover, "
                   "or reactivation. Negation in an unrelated clause is not an exemption.")
    return result


_paragraph_break = re.compile(r"(\r?\n[ \t]*\r?\n(?:[ \t]*\r?\n)*)")
_sentence_break = re.compile(r"""[.!?](?:["'”’)])?(\s+)(?=[A-Z0-9*#\-\[])""")
_abbreviation = re.compile(
    r"(?:\b(?:[A-Za-z]\.){2,}|\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc)\.)$", re.I)
_report_prefix = re.compile(
    r"^(?P<prefix>[ \t]*(?:(?:[-*+]|\d+[.)])\s+)?"
    r"(?:\*\*[^*\r\n]{1,100}:\*\*|\*\*[^*\r\n]{1,100}\*\*:|"
    r"__[^\r\n]{1,100}:__|[A-Za-z][A-Za-z0-9 /&()–—-]{0,99}:)[ \t]*)"
    r"(?P<claim>.*?)(?P<tail>[ \t]*)$")
_line_marker = re.compile(r"^(?P<prefix>[ \t]*(?:#{1,6}|[-*+]|\d+[.)])\s+)")


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


def _blocks(paragraph):
    """Keep report labels, bullets and table rows separate from adjacent prose."""
    prose = []
    for line in paragraph.splitlines(keepends=True):
        if _report_prefix.match(line.rstrip("\r\n")) or _line_marker.match(line) or line.lstrip().startswith("|"):
            if prose:
                yield "prose", "".join(prose)
                prose = []
            yield "line", line
        else:
            prose.append(line)
    if prose:
        yield "prose", "".join(prose)


def parts(text):
    return [body for paragraph in _paragraph_break.split(text or "")[::2]
            for _, block in _blocks(paragraph)
            for body, _ in _sentence_units(block) if body.strip()]


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
        if hypothetical and re.search(r"\bif\b", re.split(
                r"[;.!?]|\bbut\b|\bhowever\b", after, flags=re.I)[0], re.I):
            continue
        return True
    return False


def methodology_violation(text):
    if not _components.search(text):
        return False
    if _affirmed(_reactivation, text):
        return True
    if not (_inactive_status.search(text) and _market_state.search(text)):
        return False
    if ":" in text:
        left, right = text.split(":", 1)
        if (_components.search(left) and _inactive_status.search(left)
                and _affirmed(_market_state, right)):
            return True
    return _affirmed(_causal, text) or _affirmed(_component_state, text)


def storage_violation(text, context):
    if not _storage.search(text):
        return False
    if re.search(r"90\s*%.*(?:seasonal norm|seasonal average)|"
                 r"(?:seasonal norm|seasonal average).*90\s*%", text, re.I):
        return True
    if not context or not context.get("verified"):
        return bool(_affirmed(_comparison, text) or _affirmed(_adequate, text)
                    or _affirmed(_scarce, text, hypothetical=True)
                    or _affirmed(_storage_assurance, text, hypothetical=True))
    delta = context["deviation_pp"]
    if delta < 0 and _affirmed(re.compile(r"\babove\b.{0,35}(?:average|norm)", re.I), text):
        return True
    if delta > 0 and _affirmed(re.compile(r"\bbelow\b.{0,35}(?:average|norm)", re.I), text):
        return True
    if abs(delta) > 5 and re.search(r"\bin line\b", text, re.I):
        return True
    if delta < -5:
        return (_affirmed(_adequate, text)
                or _affirmed(_storage_assurance, text, hypothetical=True))
    if delta > 5:
        return _affirmed(_scarce, text, hypothetical=True)
    return False


def bad_sentence(text, context, methodology=False):
    return (methodology and methodology_violation(text)) or storage_violation(text, context)


def violations(text, context, methodology=False):
    return [p for p in parts(text) if bad_sentence(p, context, methodology)]


def sanitize(text, context, methodology=False):
    """Retain paragraph delimiters; append once in the first affected paragraph."""
    chunks = _paragraph_break.split(text or "")
    replacement = sentence(context)
    inserted = bool(replacement and replacement in (text or ""))
    changed = False
    for index in range(0, len(chunks), 2):
        output = []
        storage_removed = False
        paragraph_changed = False
        for kind, block in _blocks(chunks[index]):
            raw_line = block.rstrip("\r\n")
            ending = block[len(raw_line):]
            if kind == "line" and storage_violation(raw_line, context) and not (
                    methodology and methodology_violation(raw_line)):
                label = _report_prefix.match(raw_line)
                marker = _line_marker.match(raw_line)
                if raw_line.lstrip().startswith("|"):
                    cells = raw_line.split("|")
                    for cell_index, cell in enumerate(cells):
                        if not storage_violation("Storage " + cell, context):
                            continue
                        leading = re.match(r"[ \t]*", cell).group()
                        trailing = re.search(r"[ \t]*$", cell).group()
                        cells[cell_index] = leading + replacement + trailing
                    rewritten = "|".join(cells)
                else:
                    prefix = label["prefix"] if label else marker["prefix"] if marker else ""
                    tail = label["tail"] if label else re.search(r"[ \t]*$", raw_line).group()
                    rewritten = prefix + replacement + tail
                output.append(rewritten + ending)
                inserted = inserted or bool(replacement)
                paragraph_changed = True
                continue
            units = _sentence_units(block)
            kept = []
            for body, space in units:
                method_bad = methodology and methodology_violation(body)
                storage_bad = storage_violation(body, context)
                if method_bad or storage_bad:
                    paragraph_changed = True
                    storage_removed = storage_removed or (storage_bad and not method_bad)
                else:
                    kept.append(body + space)
            output.append("".join(kept))
        if not paragraph_changed:
            continue
        changed = True
        trailing = re.search(r"[ \t\r\n]*$", chunks[index]).group()
        retained = "".join(output).rstrip(" \t\r\n")
        if storage_removed and replacement and not inserted:
            retained = retained.rstrip(" \t\r\n") + (" " if retained.strip() else "") + replacement
            inserted = True
        chunks[index] = retained + trailing
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
                text, scope["context"], scope["methodology"])
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
