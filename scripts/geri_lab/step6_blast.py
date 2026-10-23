"""Static direct-reader evidence and conservative import-graph downstream inventory."""
import ast
from collections import defaultdict
import re

from .step5_data import PROJECT
from .step6_data import OUT
from .step4_data import dump
from .step4_pairs import write_csv

FIELDS = ("risk_events", "risk_indices", "asset_risk", "ai_summary", "ai_impact_json")


def build():
    modules, direct, imports = {}, [], {}
    for path in sorted((PROJECT / "src").rglob("*.py")):
        relative = str(path.relative_to(PROJECT))
        if "/tests/" in relative:
            continue
        text = path.read_text()
        module = ".".join(path.relative_to(PROJECT).with_suffix("").parts)
        modules[module] = relative
        hits = [(i, line.strip()) for i, line in enumerate(text.splitlines(), 1)
                if any(re.search(r"\b"+field+r"\b", line) for field in FIELDS)]
        if hits and not any(name in relative for name in ("pipeline_v2", "migrations.py")):
            direct.append({"module": module, "path": relative,
                           "fields": [field for field in FIELDS if re.search(r"\b"+field+r"\b", text)],
                           "references": [{"line": i, "text": line} for i, line in hits],
                           "static_routes": re.findall(r"@(?:router|app)\.(?:get|post)\(['\"]([^'\"]+)", text)})
        targets = set()
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                targets.update(x.name for x in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parent = module.split(".")[:-node.level]
                    base = ".".join(parent + ([base] if base else []))
                targets.add(base)
                targets.update(f"{base}.{x.name}" for x in node.names)
        imports[module] = targets
    reverse = defaultdict(set)
    for user, targets in imports.items():
        for target in targets:
            if target in modules:
                reverse[target].add(user)
    downstream = []
    for reader in direct:
        visited, frontier, depth = {reader["module"]}, {reader["module"]}, 0
        while frontier:
            depth += 1
            following = set()
            for origin in frontier:
                for child in reverse[origin]:
                    if child not in visited:
                        visited.add(child)
                        following.add(child)
                        downstream.append({"direct_reader": reader["path"], "dependent": modules[child],
                                           "import_distance": depth,
                                           "certainty": "potential import dependency; not proof every code path consumes stale data"})
            frontier = following
    dump(OUT / "blast_radius_direct_readers.json", direct)
    write_csv(OUT / "blast_radius_direct_readers.csv", [
        {"path": r["path"], "fields": r["fields"], "lines": [x["line"] for x in r["references"]],
         "static_routes": r["static_routes"]} for r in direct])
    write_csv(OUT / "blast_radius_import_dependents.csv", downstream)
    return direct, downstream
