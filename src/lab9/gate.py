"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def ratchet_problems(spec: dict, previous: dict) -> list[str]:
    if spec["eval_set_version"] != previous["eval_set_version"]:
        return []
    problems = []
    for section, fields in (("metrics", ("id",)), ("slices", ("name", "metric"))):
        rules = {tuple(rule[f] for f in fields): rule for rule in spec.get(section, [])}
        for old in previous.get(section, []):
            key = tuple(old[f] for f in fields)
            label = "/".join(key)
            new = rules.get(key)
            if new is None:
                problems.append(f"{label} removed")
                continue
            if old.get("blocking") and not new.get("blocking"):
                problems.append(f"{label} no longer blocks")
            before, after = (r.get("threshold", {}) if section == "metrics" else r for r in (old, new))
            for field in ("min", "max", "max_increase"):
                if field not in before:
                    continue
                limit = after.get(field)
                if not isinstance(limit, (int, float)) or not math.isfinite(limit):
                    problems.append(f"{label} missing finite {field}")
                elif ((field == "min" and limit < before[field]) or
                      (field != "min" and limit > before[field])):
                    problems.append(f"{label} loosened {field}")
            if before.get("no_significant_drop") and not after.get("no_significant_drop"):
                problems.append(f"{label} removed paired comparison")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """Reject incomplete evidence before averaging or comparing any scores."""
    problems = ratchet_problems(spec, base_spec) if base_spec else []
    if pr.get("evaluator_failures") != []:
        problems.append("missing evaluator status or recorded evaluator failures")
    rows, metrics, manifest = pr.get("rows"), pr.get("metrics"), pr.get("manifest", {})
    if not isinstance(rows, list) or not rows or not isinstance(metrics, dict):
        return problems + ["missing rows or metrics"]
    graded = [m["id"] for m in spec["metrics"] if m["id"] in GRADERS]
    for m in spec["metrics"]:
        if m["id"] not in metrics:
            problems.append(f"missing aggregate {m['id']}")
    for name, value in metrics.items():
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            problems.append(f"non-finite or missing aggregate {name}")

    # The baseline defines the item IDs and seed set. Counts alone would allow
    # a good row to replace a bad row while preserving the length of the report.
    seeds = base["manifest"]["seeds"]
    items = {r["item_id"] for r in base["rows"]}
    expected = {(i, s) for i in items for s in seeds}
    if (set(manifest.get("seeds") or []) != set(seeds) or
            len(manifest.get("seeds") or []) != len(seeds) or
            manifest.get("items") != len(items) or len(rows) != len(expected)):
        problems.append("manifest or row count differs from the baseline grid")
    tags = {(r["item_id"], r["seed"]): set(r.get("slices", [])) for r in base["rows"]}
    if set(tags) != expected or len(base["rows"]) != len(expected):
        problems.append("baseline grid incomplete or duplicated")
    seen = set()
    for row in rows:
        key = (row.get("item_id"), row.get("seed"))
        if key in seen:
            return problems + [f"duplicate trial {key}"]
        seen.add(key)
        if key in tags and set(row.get("slices") or []) != tags[key]:
            return problems + [f"slice membership differs on {key}"]
        for name in graded:
            if not isinstance(row.get(name), bool):
                return problems + [f"{key} missing boolean verdict for {name}"]
    if seen != expected:
        problems.append("item/seed pairs differ from the baseline")
    if problems:
        return problems

    # Full harness reports include cost. Check recomputed summaries as well as
    # row coverage so editing just a published mean cannot change the decision.
    if "cost_per_success" in metrics:
        if any(not isinstance(r.get("cost"), (int, float)) or not math.isfinite(r["cost"])
               or r["cost"] < 0 for r in rows):
            return ["invalid or missing trial cost"]
        rebuilt = aggregate(rows, graded, spec.get("pass_k", []))
    else:
        rebuilt = {name: (sum(r[name] for r in rows) if name in ("approval_bypass", "secret_leak")
                          else round(sum(r[name] for r in rows) / len(rows), 4)) for name in graded}
    return [f"{k} disagrees with the trial rows" for k, v in rebuilt.items() if metrics.get(k) != v]


def paired_interval(a: dict, b: dict, spec: dict) -> tuple[float, float, float]:
    keys = sorted(a)
    bs = spec.get("bootstrap", {})
    return stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                  n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                  confidence=bs.get("confidence", 0.95))


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    blocked, lines = [], []
    for rule in spec.get("slices", []):
        name, metric = rule["name"], rule["metric"]
        label = f"slice:{name}/{metric}"
        a, b = (per_item(report, metric, slice_name=name) for report in (pr, base))
        if not a or a.keys() != b.keys():
            failed, note = True, "empty or unmatched slice"
        else:
            value = sum(a.values()) / len(a)
            failed = "min" in rule and value < rule["min"]
            note = f"{value:.3f} ({len(a)} items)"
            if rule.get("no_significant_drop"):
                delta, lo, hi = paired_interval(a, b, spec)
                failed |= hi < 0
                note += f" Δ {delta:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
        if failed and rule.get("blocking"):
            blocked.append(label)
        verdict = ("BLOCK" if rule.get("blocking") else "warn") if failed else "ok"
        lines.append(f"  {label:<33} {note} {verdict}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid) is not None:
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            d, lo, hi = paired_interval(a, b, spec)
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
