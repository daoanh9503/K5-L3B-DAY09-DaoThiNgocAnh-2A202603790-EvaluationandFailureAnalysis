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
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS

SAFETY_COUNTS = {"secret_leak", "approval_bypass"}   # aggregated as a count in lab9.eval.aggregate


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows, base_rows = pr.get("rows") or [], base.get("rows") or []
    man, base_man = pr.get("manifest") or {}, base.get("manifest") or {}

    # 1. Metric values must be real numbers (NaN < min and NaN > max are both False).
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (a crashed grader must not pass as a number)")

    # 2. Graders must have run on every row.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    missing = [f"{r.get('item_id')}@{r.get('seed')}:{m}" for r in rows for m in graded if r.get(m) is None]
    if missing:
        problems.append(f"{len(missing)} graded value(s) are None, first: {missing[0]}")

    # 3. Row coverage: items x seeds, no duplicates, same (item, seed) set and manifest as main.
    seeds = list(man.get("seeds") or [])
    want = (man.get("items") or 0) * len(seeds)
    if len(rows) != want:
        problems.append(f"{len(rows)} row(s) but manifest says {man.get('items')} item x {len(seeds)} seed = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        dup = next(k for k in keys if keys.count(k) > 1)
        problems.append(f"duplicate row {dup[0]}@{dup[1]} ({len(keys) - len(set(keys))} duplicate(s))")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(keys) != base_keys:
        gone, extra = sorted(base_keys - set(keys), key=str), sorted(set(keys) - base_keys, key=str)
        problems.append(f"(item, seed) set differs from baseline: {len(gone)} missing"
                        + (f" e.g. {gone[0][0]}@{gone[0][1]}" if gone else "")
                        + f", {len(extra)} extra" + (f" e.g. {extra[0][0]}@{extra[0][1]}" if extra else ""))
    if sorted(seeds) != sorted(base_man.get("seeds") or []) or man.get("items") != base_man.get("items"):
        problems.append(f"manifest {man.get('items')} item x seeds {seeds} differs from baseline "
                        f"{base_man.get('items')} item x seeds {base_man.get('seeds')}")

    # 4. Slice tags come from labels: an item may not move in or out of a slice between runs.
    base_slices = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    for r in rows:
        iid = r.get("item_id")
        if iid in base_slices and sorted(r.get("slices") or []) != base_slices[iid]:
            problems.append(f"{iid}@{r.get('seed')} slices {r.get('slices')} differ from baseline {base_slices[iid]}")
            break

    # 5. Reported metrics must be what the rows say (a hand-edited number with honest rows).
    problems += _metrics_match_rows(pr, graded)

    # 6. Ratchet: on the same eval-set version a spec may only get stricter.
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)
    return problems


def _metrics_match_rows(rep: dict, graded: list[str]) -> list[str]:
    rows = rep.get("rows") or []
    out = []
    for m in graded:
        reported = (rep.get("metrics") or {}).get(m)
        vals = [r[m] for r in rows if r.get(m) is not None]
        if not vals or not isinstance(reported, (int, float)) or isinstance(reported, bool):
            continue
        want = sum(vals) if m in SAFETY_COUNTS else round(sum(vals) / len(vals), 4)
        if abs(float(reported) - want) > 1e-6:
            out.append(f"metric {m} reported {reported} but rows give {want}")
    return out


def _looser(th: dict, base_th: dict) -> list[str]:
    out = []
    if "max" in base_th and ("max" not in th or th["max"] > base_th["max"]):
        out.append(f"max {base_th['max']} -> {th.get('max')}")
    if "min" in base_th and ("min" not in th or th["min"] < base_th["min"]):
        out.append(f"min {base_th['min']} -> {th.get('min')}")
    if "max_increase" in base_th and ("max_increase" not in th or th["max_increase"] > base_th["max_increase"]):
        out.append(f"max_increase {base_th['max_increase']} -> {th.get('max_increase')}")
    if base_th.get("no_significant_drop") and not th.get("no_significant_drop"):
        out.append("no_significant_drop removed")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    out = []
    cur = {m["id"]: m for m in spec.get("metrics", [])}
    for bm in base_spec.get("metrics", []):
        m = cur.get(bm["id"])
        if m is None:
            out.append(f"ratchet: metric {bm['id']} removed")
            continue
        if bm.get("blocking") and not m.get("blocking"):
            out.append(f"ratchet: metric {bm['id']} no longer blocking")
        out += [f"ratchet: metric {bm['id']} {x}" for x in _looser(m.get("threshold") or {}, bm.get("threshold") or {})]
    cur_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        s = cur_s.get((bs["name"], bs["metric"]))
        tag = f"slice {bs['name']}/{bs['metric']}"
        if s is None:
            out.append(f"ratchet: {tag} removed")
            continue
        if bs.get("blocking") and not s.get("blocking"):
            out.append(f"ratchet: {tag} no longer blocking")
        out += [f"ratchet: {tag} {x}" for x in _looser(s, bs)]
    for key in ("seeds", "pass_k", "eval_set", "labels"):
        if key in base_spec and spec.get(key) != base_spec[key]:
            out.append(f"ratchet: {key} changed {base_spec[key]} -> {spec.get(key)}")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"            # a slice with no rows cannot vouch for anything
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if "max" in s and val > s["max"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if s.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<38} {val!s:<8} n={len(a):<3} {json.dumps(th):<36} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
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
