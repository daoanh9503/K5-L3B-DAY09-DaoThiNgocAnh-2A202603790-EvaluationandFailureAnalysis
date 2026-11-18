"""M1 evidence: which eval items does each single-bug variant break?

    cd src && python scripts/fm_probe.py

Each FM-xx is probed with a variant that turns on exactly one bug switch from
lab9/variant_agent.py (plus "no_override", the honest baseline). An item is tagged
with FM-xx iff that variant fails it on at least one seed. The baseline `swarm`
is probed too, so weaknesses of the reference agent show up as well.
Runs on fresh temp stores; no Lab 8 file is touched.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab8.console import utf8_stdio  # noqa: E402
from lab8.db import load_json, load_jsonl  # noqa: E402
from lab8.shapes import SHAPES  # noqa: E402
from lab9 import variants  # noqa: E402
from lab9.eval import WORLD, make_task  # noqa: E402
from lab9.variant_agent import make_shape  # noqa: E402

BUGS = {"FM-01": "leaky_trace", "FM-02": "ignore_denied", "FM-03": "ticket_trust", "FM-04": "sum_parts",
        "FM-05": "pre_deducted", "FM-06": "stale_clause", "FM-07": "sibling_refund", "FM-08": "misreport"}
SEEDS = [11, 22, 33, 44, 55]
AMOUNT = re.compile(r"hoàn (?:phí )?([\d.]+)đ")


def reply_amount(events: list[dict]) -> int | None:
    for e in events:
        if e.get("kind") == "reply":
            m = AMOUNT.search(e["payload"].get("text", ""))
            return int(m.group(1).replace(".", "")) if m else None
    return None


def failure(t: dict, label: dict, check_reply: bool) -> str | None:
    """check_reply only for FM-08: other variants (e.g. pre_deducted) also echo their own number,
    but that symptom is FM-08's definition, not theirs."""
    if any(s and s in t["blob"] for s in label["forbid_substrings"]):
        return "secret_leak"
    if t["unexpected_rows"]:
        return "unexpected_ledger_rows"
    if not t["lab8_pass"]:
        return t["lab8_reason"]
    said = reply_amount(t["events"]) if check_reply else None
    if said is not None and said != t["snapshot"].get("refund_vnd"):
        return f"reply_says_{said}_ledger_{t['snapshot'].get('refund_vnd')}"
    return None


def main() -> int:
    utf8_stdio()
    variants.register()
    shapes = {"swarm": "swarm"}
    for fm, bug in BUGS.items():
        SHAPES[f"probe_{bug}"] = make_shape(f"probe_{bug}", {"no_override", bug})
        shapes[fm] = f"probe_{bug}"
    claims = load_jsonl(Path("data/public_claims.jsonl"))
    labels = {c["claim_id"]: c["expected"] for c in claims}
    tags: dict[str, list[str]] = {c["claim_id"]: [] for c in claims}
    with tempfile.TemporaryDirectory(prefix="lab9-probe-", ignore_cleanup_errors=True) as tmp:
        for fm, shape in shapes.items():
            task = make_task(shape, load_json(WORLD), claims, labels, Path(tmp))
            print(f"== {fm} ({shape})")
            for c in claims:
                cid = c["claim_id"]
                bad = [(s, why) for s in SEEDS
                       if (why := failure(task({"claim_id": cid, "seed": s}), labels[cid], fm == "FM-08"))]
                if bad:
                    print(f"   {cid}: fails {len(bad)}/5 seeds, first @{bad[0][0]}: {bad[0][1]}")
                    if fm != "swarm":
                        tags[cid].append(fm)
    print("== failure_modes per claim")
    for cid, fms in tags.items():
        print(f"   {cid}: {fms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
