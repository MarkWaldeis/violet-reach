#!/usr/bin/env python3
"""Violet Reach asset pipeline. Standard library only; Blender is called as a subprocess.

  vr.py status                      list every asset and its gate status
  vr.py new <category> <id>         create an asset folder with asset.json and a build.py stub
  vr.py build <id>                  run build.py in Blender, write <id>.blend
  vr.py sheet <id> [--draft]        render the review sheet (status -> blender_review)
  vr.py review <id> --reviewer R --scores silhouette=9,... [--notes TEXT]
                                    record a review; approves only if every score passes
  vr.py export <id>                 bake + LODs + .glb; refuses anything not approved
  vr.py check                       the gate, run by CI: fails if anything unapproved ships
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
BLENDER_TOOLS = os.path.join(ROOT, "tools", "blender")
WEB_ASSETS = os.path.join(ROOT, "web", "public", "assets")
PLACEMENTS = os.path.join(ROOT, "world", "placements.json")

STATUSES = ["planned", "modeling", "blender_review", "approved", "exported", "in_game"]
SHIPPABLE = {"approved", "exported", "in_game"}
CRITERIA = ["silhouette", "form_detail", "material", "scale", "style", "defects"]
PASS_SCORE = 8


class GateError(Exception):
    pass


def asset_dirs():
    for category in sorted(os.listdir(ASSETS)):
        cat_dir = os.path.join(ASSETS, category)
        if not os.path.isdir(cat_dir):
            continue
        for asset_id in sorted(os.listdir(cat_dir)):
            if os.path.isfile(os.path.join(cat_dir, asset_id, "asset.json")):
                yield os.path.join(cat_dir, asset_id)


def find(asset_id):
    for d in asset_dirs():
        if os.path.basename(d) == asset_id:
            return d
    raise SystemExit(f"unknown asset: {asset_id}")


def load(asset_dir):
    with open(os.path.join(asset_dir, "asset.json")) as f:
        return json.load(f)


def save(asset_dir, meta):
    with open(os.path.join(asset_dir, "asset.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def source_hash(asset_dir):
    return sha256(os.path.join(asset_dir, "build.py"))


def gate_problems(asset_dir, meta):
    """Why this asset may not go into the game. Empty list means it passes the Blender gate."""
    problems = []
    review = meta.get("review")
    if meta.get("status") not in SHIPPABLE:
        problems.append(f"status is '{meta.get('status')}', needs one of {sorted(SHIPPABLE)}")
    if not review:
        return problems + ["no review recorded"]
    if not review.get("reviewer"):
        problems.append("review has no reviewer")
    elif review["reviewer"] == meta.get("builder"):
        problems.append("reviewer is the builder; a different session must review")
    scores = review.get("scores", {})
    for c in CRITERIA:
        if not isinstance(scores.get(c), int):
            problems.append(f"missing score: {c}")
        elif scores[c] < PASS_SCORE:
            problems.append(f"score {c}={scores[c]} is below {PASS_SCORE}")
    if review.get("source_sha256") != source_hash(asset_dir):
        problems.append("build.py changed after the review; render a new sheet and review again")
    sheet = os.path.join(asset_dir, "review", "sheet.jpg")
    if not os.path.isfile(sheet):
        problems.append("review/sheet.jpg is missing")
    elif review.get("sheet_sha256") != sha256(sheet):
        problems.append("review/sheet.jpg is not the sheet that was reviewed")
    return problems


def blender(args, blend=None):
    exe = os.environ.get("BLENDER", "blender")
    cmd = [exe, "-b"] + ([blend] if blend else ["--factory-startup"]) + args
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    result = [line for line in proc.stdout.splitlines() if line.startswith("VR_RESULT")]
    if proc.returncode != 0 or not result:
        sys.stderr.write(proc.stdout[-4000:])
        raise SystemExit("Blender step failed")
    print(result[-1])


def blend_file(asset_dir):
    return os.path.join(asset_dir, os.path.basename(asset_dir) + ".blend")


def cmd_status(_):
    rows = [(os.path.basename(d), load(d)) for d in asset_dirs()]
    width = max((len(r[0]) for r in rows), default=10)
    for asset_id, meta in rows:
        print(f"{asset_id:<{width}}  {meta['category']:<12} {meta['status']}")
    print(f"{len(rows)} assets, {sum(m['status'] in SHIPPABLE for _, m in rows)} past the Blender gate")


def cmd_new(a):
    d = os.path.join(ASSETS, a.category, a.id)
    if os.path.exists(d):
        raise SystemExit(f"{d} already exists")
    os.makedirs(d)
    save(d, {"id": a.id, "category": a.category, "title": a.id, "description": "",
             "target_size_m": [1, 1, 1], "lod_triangles": [12000, 4000, 1000], "texture_size": 2048,
             "status": "planned", "builder": None, "review": None})
    with open(os.path.join(d, "build.py"), "w") as f:
        f.write('"""Describe the object. Units are metres, origin at ground centre, Z up."""\n'
                "import bpy\n\nimport vrlib\n\n\ndef build():\n"
                "    # Create mesh objects and put each one in the SOURCE collection with vrlib.link_to_source(obj).\n"
                "    raise NotImplementedError\n")
    print(d)


def cmd_build(a):
    d = find(a.id)
    blender(["--python", os.path.join(BLENDER_TOOLS, "run_build.py"), "--", d])
    meta = load(d)
    if meta["status"] == "planned":
        meta["status"] = "modeling"
    if a.builder:
        meta["builder"] = a.builder
    save(d, meta)


def cmd_sheet(a):
    d = find(a.id)
    extra = ["--draft"] if a.draft else []
    if a.samples:
        extra += ["--samples", str(a.samples)]
    blender(["--python", os.path.join(BLENDER_TOOLS, "render_sheet.py"), "--", d] + extra, blend=blend_file(d))
    if a.draft:
        return
    meta = load(d)
    # A new sheet always needs a new review.
    meta["status"] = "blender_review"
    meta["review"] = None
    save(d, meta)


def cmd_review(a):
    d = find(a.id)
    meta = load(d)
    if meta["status"] != "blender_review":
        raise SystemExit(f"{a.id} is '{meta['status']}'; render the sheet first (vr.py sheet {a.id})")
    try:
        scores = {k: int(v) for k, v in (pair.split("=") for pair in a.scores.split(","))}
    except ValueError:
        raise SystemExit("--scores wants name=int pairs, e.g. silhouette=9,form_detail=8")
    if sorted(scores) != sorted(CRITERIA):
        raise SystemExit(f"--scores needs exactly: {', '.join(CRITERIA)}")
    if any(not 1 <= v <= 10 for v in scores.values()):
        raise SystemExit("scores run from 1 to 10")
    if a.reviewer == meta.get("builder"):
        raise SystemExit("the builder cannot review their own asset")
    meta["review"] = {"reviewer": a.reviewer, "scores": scores, "notes": a.notes or "",
                      "round": (meta.get("review_rounds", 0) + 1),
                      "source_sha256": source_hash(d),
                      "sheet_sha256": sha256(os.path.join(d, "review", "sheet.jpg"))}
    meta["review_rounds"] = meta["review"]["round"]
    passed = all(v >= PASS_SCORE for v in scores.values())
    meta["status"] = "approved" if passed else "modeling"
    save(d, meta)
    print(f"{a.id}: {'approved' if passed else 'rejected, back to modeling'}")


def cmd_export(a):
    d = find(a.id)
    meta = load(d)
    problems = gate_problems(d, meta)
    if problems:
        raise SystemExit(f"{a.id} has not passed the Blender gate:\n  - " + "\n  - ".join(problems))
    blender(["--python", os.path.join(BLENDER_TOOLS, "export_asset.py"), "--", d], blend=blend_file(d))
    raw = os.path.join(d, "export", a.id + ".raw.glb")
    out = os.path.join(d, "export", a.id + ".glb")
    gltf = ["npx", "--no-install", "gltf-transform"]
    web = os.path.join(ROOT, "web")
    tmp = raw + ".tmp.glb"
    subprocess.run(gltf + ["webp", raw, tmp, "--quality", "92"], cwd=web, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(gltf + ["meshopt", tmp, out], cwd=web, check=True, stdout=subprocess.DEVNULL)
    os.remove(raw)
    os.remove(tmp)
    if meta["status"] == "approved":
        meta["status"] = "exported"
    meta["export"] = {"file": f"export/{a.id}.glb", "bytes": os.path.getsize(out), "sha256": sha256(out),
                      "source_sha256": source_hash(d)}
    save(d, meta)
    sync_web()
    print(f"{a.id}: exported {meta['export']['bytes'] / 1e6:.2f} MB")


def sync_web():
    """Copy gated exports into web/public/assets and write the manifest the runtime loads."""
    os.makedirs(WEB_ASSETS, exist_ok=True)
    manifest = []
    keep = {"manifest.json"}
    for d in asset_dirs():
        meta = load(d)
        export = meta.get("export")
        if not export or gate_problems(d, meta):
            continue
        name = meta["id"] + ".glb"
        shutil.copyfile(os.path.join(d, export["file"]), os.path.join(WEB_ASSETS, name))
        keep.add(name)
        manifest.append({"id": meta["id"], "category": meta["category"], "title": meta["title"], "file": name,
                         "size_m": meta.get("size_m", meta["target_size_m"]), "bytes": export["bytes"]})
    for name in os.listdir(WEB_ASSETS):
        if name not in keep:
            os.remove(os.path.join(WEB_ASSETS, name))
    with open(os.path.join(WEB_ASSETS, "manifest.json"), "w") as f:
        json.dump({"assets": manifest}, f, indent=2, ensure_ascii=False)
        f.write("\n")


def cmd_check(_):
    errors = []
    by_id = {}
    for d in asset_dirs():
        meta = load(d)
        rel = os.path.relpath(d, ROOT)
        by_id[meta["id"]] = (d, meta)
        if meta["id"] != os.path.basename(d) or meta["category"] != os.path.basename(os.path.dirname(d)):
            errors.append(f"{rel}: id/category do not match the folder")
        if meta["status"] not in STATUSES:
            errors.append(f"{rel}: unknown status '{meta['status']}'")
        problems = gate_problems(d, meta)
        ships = meta["status"] in SHIPPABLE or os.path.isdir(os.path.join(d, "export"))
        if ships and problems:
            errors += [f"{rel}: {p}" for p in problems]
        export = meta.get("export")
        if export:
            path = os.path.join(d, export["file"])
            if not os.path.isfile(path) or sha256(path) != export["sha256"]:
                errors.append(f"{rel}: exported .glb does not match asset.json")
            if export["source_sha256"] != source_hash(d):
                errors.append(f"{rel}: build.py changed after export")
    # Nothing may sit in the web folder unless it is the export of a gated asset.
    if os.path.isdir(WEB_ASSETS):
        for name in sorted(os.listdir(WEB_ASSETS)):
            if not name.endswith(".glb"):
                continue
            entry = by_id.get(name[:-4])
            if not entry or gate_problems(*entry) or not entry[1].get("export"):
                errors.append(f"web/public/assets/{name}: not the export of an approved asset")
            elif sha256(os.path.join(WEB_ASSETS, name)) != entry[1]["export"]["sha256"]:
                errors.append(f"web/public/assets/{name}: differs from the approved export")
    if os.path.isfile(PLACEMENTS):
        with open(PLACEMENTS) as f:
            for item in json.load(f).get("placements", []):
                entry = by_id.get(item["asset"])
                if not entry or not entry[1].get("export") or gate_problems(*entry):
                    errors.append(f"world/placements.json: '{item['asset']}' has not passed the Blender gate")
    for e in errors:
        print("GATE FAIL:", e)
    if errors:
        raise SystemExit(1)
    print(f"gate ok: {len(by_id)} assets checked")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("new"); s.add_argument("category"); s.add_argument("id"); s.set_defaults(fn=cmd_new)
    s = sub.add_parser("build"); s.add_argument("id"); s.add_argument("--builder"); s.set_defaults(fn=cmd_build)
    s = sub.add_parser("sheet"); s.add_argument("id"); s.add_argument("--draft", action="store_true")
    s.add_argument("--samples", type=int); s.set_defaults(fn=cmd_sheet)
    s = sub.add_parser("review"); s.add_argument("id"); s.add_argument("--reviewer", required=True)
    s.add_argument("--scores", required=True); s.add_argument("--notes"); s.set_defaults(fn=cmd_review)
    s = sub.add_parser("export"); s.add_argument("id"); s.set_defaults(fn=cmd_export)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
