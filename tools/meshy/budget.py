"""Meshy credit book for Violet Reach (GRAFIK_PLAN.md section 8).

The ledger lives outside the repo in $VR_MESHY_DIR/ledger.csv (default:
Desktop\\Violet Reach Meshy). Every paid call gets one row *before* it is
submitted (expected credits, actual empty) and is completed afterwards with the
task id, the actual credits and the balance. Rows without an actual value count
with their expected value, so an in-flight call is always reserved.

  python tools/meshy/budget.py summary
  python tools/meshy/budget.py check  --post class_b --estimate 15
  python tools/meshy/budget.py reserve --asset boulder_chalk_a --step model --post pilot \
        --resource image-to-3d --model meshy-t2.5 --estimate 15          -> prints row number
  python tools/meshy/budget.py complete --row 3 --task-id <id> --actual 15 --balance 3130 \
        --verdict ok --file boulder_chalk_a/model/raw.glb

Exit code 2 means the call must not be made.
"""
import argparse
import csv
import datetime
import os
import sys

LIB = os.environ.get("VR_MESHY_DIR", os.path.join(os.path.expanduser("~"), "Desktop", "Violet Reach Meshy"))
LEDGER = os.path.join(LIB, "ledger.csv")
FIELDS = ["date", "asset", "step", "post", "resource", "task_id", "model",
          "expected", "actual", "balance_after", "verdict", "file"]
POSTS = {"pilot": 150, "images": 280, "class_a": 420, "class_b": 330,
         "rollout": 300, "rework": 320, "reserve": 200}
TOTAL_CAP = 2000
STOP_AT = 1800  # section 13: stop and ask Mark


def rows():
    with open(LEDGER, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(all_rows):
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(all_rows)
    os.replace(tmp, LEDGER)


def cost(row):
    value = row["actual"] if row["actual"] != "" else row["expected"]
    return float(value or 0)


def totals(all_rows):
    per_post = {p: 0.0 for p in POSTS}
    for r in all_rows:
        per_post[r["post"]] = per_post.get(r["post"], 0.0) + cost(r)
    return sum(per_post.values()), per_post


def verdict(post, estimate, allow_reserve=False):
    if post not in POSTS:
        return f"unknown post '{post}' (one of {', '.join(POSTS)})"
    if post == "reserve" and not allow_reserve:
        return "the reserve needs Mark's approval (--allow-reserve)"
    total, per_post = totals(rows())
    if per_post[post] + estimate > POSTS[post]:
        return f"post '{post}' would reach {per_post[post] + estimate:g} of {POSTS[post]}; shorten the asset list"
    if total + estimate >= STOP_AT:
        return f"total would reach {total + estimate:g} (stop at {STOP_AT}); ask Mark"
    return None


def cmd_summary(_):
    total, per_post = totals(rows())
    for p, limit in POSTS.items():
        print(f"{p:<8} {per_post[p]:>7g} / {limit}")
    print(f"{'total':<8} {total:>7g} / {TOTAL_CAP}  (stop at {STOP_AT})")


def cmd_check(a):
    problem = verdict(a.post, a.estimate, a.allow_reserve)
    if problem:
        print("REFUSED:", problem)
        sys.exit(2)
    print("ok")


def cmd_reserve(a):
    problem = verdict(a.post, a.estimate, a.allow_reserve)
    if problem:
        print("REFUSED:", problem)
        sys.exit(2)
    all_rows = rows()
    all_rows.append({"date": datetime.date.today().isoformat(), "asset": a.asset, "step": a.step,
                     "post": a.post, "resource": a.resource, "task_id": "", "model": a.model,
                     "expected": f"{a.estimate:g}", "actual": "", "balance_after": "",
                     "verdict": "pending", "file": ""})
    write(all_rows)
    print(len(all_rows))


def cmd_complete(a):
    all_rows = rows()
    r = all_rows[a.row - 1]
    for key in ("task_id", "actual", "balance_after", "verdict", "file"):
        value = getattr(a, key)
        if value is not None:
            r[key] = f"{value:g}" if isinstance(value, float) else value
    write(all_rows)
    if r["actual"] != "" and abs(float(r["actual"]) - float(r["expected"])) > 0.5:
        print(f"WARNING: actual {r['actual']} differs from expected {r['expected']}; recheck the price table")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("summary").set_defaults(fn=cmd_summary)
    c = sub.add_parser("check")
    c.add_argument("--post", required=True)
    c.add_argument("--estimate", type=float, required=True)
    c.add_argument("--allow-reserve", action="store_true")
    c.set_defaults(fn=cmd_check)
    r = sub.add_parser("reserve")
    for name in ("asset", "step", "post", "resource", "model"):
        r.add_argument(f"--{name}", required=True)
    r.add_argument("--estimate", type=float, required=True)
    r.add_argument("--allow-reserve", action="store_true")
    r.set_defaults(fn=cmd_reserve)
    d = sub.add_parser("complete")
    d.add_argument("--row", type=int, required=True)
    d.add_argument("--task-id", dest="task_id")
    d.add_argument("--actual", type=float)
    d.add_argument("--balance", dest="balance_after")
    d.add_argument("--verdict")
    d.add_argument("--file")
    d.set_defaults(fn=cmd_complete)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
