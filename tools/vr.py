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
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from placement_format import placement_problems

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
BLENDER_TOOLS = os.path.join(ROOT, "tools", "blender")
WEB_ASSETS = os.path.join(ROOT, "web", "public", "assets")
PLACEMENTS = os.path.join(ROOT, "world", "placements.json")

STATUSES = ["planned", "modeling", "blender_review", "approved", "exported", "in_game"]
SHIPPABLE = {"approved", "exported", "in_game"}
CRITERIA = ["silhouette", "form_detail", "material", "scale", "style", "defects"]
PASS_SCORE = 8


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
    with open(os.path.join(asset_dir, "asset.json"), encoding="utf-8") as f:
        return json.load(f)


def save(asset_dir, meta):
    with open(os.path.join(asset_dir, "asset.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def source_hash(asset_dir):
    inputs = [os.path.join(asset_dir, "build.py")]
    inputs += [os.path.join(BLENDER_TOOLS, name) for name in ("run_build.py", "vrlib.py")]
    meshy_meta = os.path.join(asset_dir, "meshy.json")
    if os.path.isfile(meshy_meta):
        inputs.append(meshy_meta)
    tree = ast.parse(Path(inputs[0]).read_text(encoding="utf-8-sig"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.update(alias.name.split(".")[-1] for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[-1])
    if "vrmeshy" in imports:
        inputs.append(os.path.join(BLENDER_TOOLS, "vrmeshy.py"))
    if "vrmat" in imports or "vrcolumn" in imports:
        inputs += [os.path.join(BLENDER_TOOLS, "vrmat.py"), os.path.join(ROOT, "art", "palette.json")]
    if "vrcolumn" in imports:
        inputs.append(os.path.join(BLENDER_TOOLS, "vrcolumn.py"))
    return hashlib.sha256("".join(sha256(path) for path in inputs).encode()).hexdigest()


def sheet_problems(asset_dir):
    sheet = os.path.join(asset_dir, "review", "sheet.jpg")
    try:
        with open(os.path.join(asset_dir, "review", "sheet.json")) as f:
            receipt = json.load(f)
        if receipt.get("source_sha256") != source_hash(asset_dir):
            return ["build.py or Blender build tools changed; render a new sheet"]
        if receipt.get("sheet_sha256") != sha256(sheet):
            return ["review/sheet.jpg does not match the render receipt"]
    except (OSError, ValueError):
        return ["review sheet or render receipt is missing or unreadable"]
    return []


def gate_problems(asset_dir, meta):
    """Why this asset may not go into the game. Empty list means it passes the Blender gate."""
    problems = []
    review = meta.get("review")
    if meta.get("status") not in SHIPPABLE:
        problems.append(f"status is '{meta.get('status')}', needs one of {sorted(SHIPPABLE)}")
    if not review:
        return problems + ["no review recorded"]
    if not meta.get("builder"):
        problems.append("asset has no builder")
    if not review.get("reviewer"):
        problems.append("review has no reviewer")
    elif review["reviewer"] == meta.get("builder"):
        problems.append("reviewer is the builder; a different session must review")
    scores = review.get("scores", {})
    for c in CRITERIA:
        if type(scores.get(c)) is not int:
            problems.append(f"missing score: {c}")
        elif scores[c] < PASS_SCORE:
            problems.append(f"score {c}={scores[c]} is below {PASS_SCORE}")
        elif scores[c] > 10:
            problems.append(f"score {c}={scores[c]} is above 10")
    if review.get("source_sha256") != source_hash(asset_dir):
        problems.append("build.py changed after the review; render a new sheet and review again")
    sheet = os.path.join(asset_dir, "review", "sheet.jpg")
    if not os.path.isfile(sheet):
        problems.append("review/sheet.jpg is missing")
    elif review.get("sheet_sha256") != sha256(sheet):
        problems.append("review/sheet.jpg is not the sheet that was reviewed")
    return problems + sheet_problems(asset_dir)


def _default_blender():
    exe = os.environ.get("BLENDER")
    if exe:
        return exe
    if shutil.which("blender"):
        return "blender"
    win_default = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
    return win_default if os.path.isfile(win_default) else "blender"


def _ensure_ktx_path():
    if shutil.which("ktx"):
        return
    ktx_bin = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs", "KTX-Software", "bin")
    if os.path.isdir(ktx_bin):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + ktx_bin


def blender(args, blend=None):
    exe = _default_blender()
    # `blender -b <file>` hangs on this machine (Blender 5.2); start from the factory
    # scene and let open_blend.py load the file before the work script runs.
    cmd = [exe, "-b", "--factory-startup", "--python-exit-code", "1"]
    env = None
    if blend:
        cmd += ["--python", os.path.join(BLENDER_TOOLS, "open_blend.py")]
        env = dict(os.environ, VR_OPEN_BLEND=os.path.abspath(blend))
    proc = subprocess.run(cmd + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    result = [line for line in proc.stdout.splitlines() if line.startswith("VR_RESULT")]
    if proc.returncode != 0 or not result:
        sys.stderr.write(proc.stdout[-4000:])
        raise SystemExit("Blender step failed")
    print(result[-1])


def blend_file(asset_dir):
    return os.path.join(asset_dir, os.path.basename(asset_dir) + ".blend")


def build_source(asset_dir, output):
    blender(["--python", os.path.join(BLENDER_TOOLS, "run_build.py"), "--", asset_dir, output])


def cmd_status(_):
    rows = [(os.path.basename(d), load(d)) for d in asset_dirs()]
    width = max((len(r[0]) for r in rows), default=10)
    for asset_id, meta in rows:
        print(f"{asset_id:<{width}}  {meta['category']:<12} {meta['status']}")
    print(f"{len(rows)} assets, {sum(m['status'] in SHIPPABLE for _, m in rows)} past the Blender gate")


def cmd_new(a):
    if any(not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name) for name in (a.category, a.id)):
        raise SystemExit("category and id must be lowercase slugs")
    if any(os.path.basename(d) == a.id for d in asset_dirs()):
        raise SystemExit(f"asset id '{a.id}' already exists")
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
    meta = load(d)
    if a.builder and meta["status"] in SHIPPABLE and a.builder != meta.get("builder"):
        raise SystemExit("cannot change the builder of an approved asset")
    build_source(d, blend_file(d))
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
    digest = source_hash(d)
    build_source(d, blend_file(d))
    blender(["--python", os.path.join(BLENDER_TOOLS, "render_sheet.py"), "--", d] + extra, blend=blend_file(d))
    if a.draft:
        return
    if source_hash(d) != digest:
        raise SystemExit("source changed during render; render again")
    receipt_path = os.path.join(d, "review", "sheet.json")
    with open(receipt_path) as f:
        receipt = json.load(f)
    receipt.update(source_sha256=digest, sheet_sha256=sha256(os.path.join(d, "review", "sheet.jpg")))
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)
        f.write("\n")
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
    if not meta.get("builder"):
        raise SystemExit("record the builder first (vr.py build <id> --builder <session>)")
    problems = sheet_problems(d)
    if problems:
        raise SystemExit("\n".join(problems))
    try:
        scores = {k: int(v) for k, v in (pair.split("=") for pair in a.scores.split(","))}
    except ValueError:
        raise SystemExit("--scores wants name=int pairs, e.g. silhouette=9,form_detail=8")
    if sorted(scores) != sorted(CRITERIA):
        raise SystemExit(f"--scores needs exactly: {', '.join(CRITERIA)}")
    if any(not 1 <= v <= 10 for v in scores.values()):
        raise SystemExit("scores run from 1 to 10")
    if not a.reviewer.strip():
        raise SystemExit("reviewer cannot be blank")
    if a.reviewer.strip() == meta.get("builder"):
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
    digest = source_hash(d)
    out = os.path.join(d, "export", a.id + ".glb")
    gltf = [shutil.which("npx") or "npx", "--no-install", "gltf-transform"]
    web = os.path.join(ROOT, "web")
    texture_format = meta.get("texture_format", "webp")
    if texture_format not in {"webp", "ktx2"}:
        raise SystemExit(f"{a.id}: unknown texture_format '{texture_format}'")
    if texture_format == "ktx2":
        _ensure_ktx_path()
    with tempfile.TemporaryDirectory(dir=d) as work:
        scene = os.path.join(work, a.id + ".blend")
        build_source(d, scene)
        blender(["--python", os.path.join(BLENDER_TOOLS, "export_asset.py"), "--", d, work], blend=scene)
        raw = os.path.join(work, a.id + ".raw.glb")
        tmp = os.path.join(work, "tex.glb")
        packed = os.path.join(work, "packed.glb")
        if texture_format == "ktx2":
            # KTX-Software cannot read WebP, so encode straight from the PNG raw.
            etc1s = os.path.join(work, "etc1s.glb")
            subprocess.run(gltf + ["etc1s", raw, etc1s, "--slots",
                                   "{baseColorTexture,metallicRoughnessTexture,occlusionTexture,emissiveTexture}"],
                           cwd=web, check=True)
            subprocess.run(gltf + ["uastc", etc1s, tmp, "--slots", "normalTexture"], cwd=web, check=True)
        else:
            subprocess.run(gltf + ["webp", raw, tmp, "--quality", "92"], cwd=web, check=True)
        subprocess.run(gltf + ["meshopt", tmp, packed], cwd=web, check=True)
        if gate_problems(d, load(d)) or load(d) != meta or source_hash(d) != digest:
            raise SystemExit("source, sheet or approval changed during export; retry")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        os.replace(packed, out)
    if meta["status"] == "approved":
        meta["status"] = "exported"
    with open(os.path.join(d, "review", "sheet.json")) as f:
        meta["size_m"] = json.load(f)["size_m"]
    meta["export"] = {"file": f"export/{a.id}.glb", "bytes": os.path.getsize(out), "sha256": sha256(out),
                      "source_sha256": digest, "sheet_sha256": meta["review"]["sheet_sha256"],
                      "lod_triangles": meta["lod_triangles"], "texture_size": meta["texture_size"]}
    save(d, meta)
    sync_web()
    print(f"{a.id}: exported {meta['export']['bytes'] / 1e6:.2f} MB")


def _glb_webp_to_png(src_glb, dst_glb):
    """Rewrite embedded image/webp images in a GLB to image/png for gltf-transform ktx encoding."""
    import io
    from PIL import Image

    blob = Path(src_glb).read_bytes()
    magic, version, _ = struct.unpack("<4sII", blob[:12])
    if magic != b"glTF" or version != 2:
        raise ValueError(f"{src_glb}: not a glTF 2.0 binary")
    pos = 12
    gltf_json, bin_chunk = None, bytearray()
    while pos + 8 <= len(blob):
        clen, ctype = struct.unpack("<II", blob[pos:pos + 8])
        pos += 8
        cdata = blob[pos:pos + clen]
        pos += clen
        if ctype == 0x4E4F534A:  # JSON
            gltf_json = json.loads(cdata.decode("utf-8"))
        elif ctype == 0x004E4942:  # BIN
            bin_chunk = bytearray(cdata)
    if gltf_json is None:
        raise ValueError(f"{src_glb}: missing JSON chunk")

    for tex in gltf_json.get("textures", []):
        ext = tex.get("extensions") or {}
        if "EXT_texture_webp" in ext:
            if "source" not in tex and "source" in ext["EXT_texture_webp"]:
                tex["source"] = ext["EXT_texture_webp"]["source"]
            ext.pop("EXT_texture_webp", None)
            if not ext:
                tex.pop("extensions", None)
    for key in ("extensionsUsed", "extensionsRequired"):
        if key in gltf_json:
            gltf_json[key] = [e for e in gltf_json[key] if e != "EXT_texture_webp"]
            if not gltf_json[key]:
                gltf_json.pop(key, None)

    bvs = gltf_json.get("bufferViews", [])
    for img in gltf_json.get("images", []):
        if img.get("mimeType") != "image/webp" or "bufferView" not in img:
            continue
        bv = bvs[img["bufferView"]]
        off = bv.get("byteOffset", 0)
        raw = bytes(bin_chunk[off:off + bv["byteLength"]])
        buf = io.BytesIO()
        Image.open(io.BytesIO(raw)).save(buf, format="PNG")
        png_bytes = buf.getvalue()
        while len(bin_chunk) % 4 != 0:
            bin_chunk.append(0)
        new_off = len(bin_chunk)
        bin_chunk.extend(png_bytes)
        bv["byteOffset"] = new_off
        bv["byteLength"] = len(png_bytes)
        img["mimeType"] = "image/png"
    while len(bin_chunk) % 4 != 0:
        bin_chunk.append(0)
    if gltf_json.get("buffers"):
        gltf_json["buffers"][0]["byteLength"] = len(bin_chunk)

    jbytes = bytearray(json.dumps(gltf_json, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    while len(jbytes) % 4 != 0:
        jbytes.append(0x20)
    total = 12 + 8 + len(jbytes) + 8 + len(bin_chunk)
    out = bytearray()
    out.extend(struct.pack("<4sII", b"glTF", 2, total))
    out.extend(struct.pack("<II", len(jbytes), 0x4E4F534A))
    out.extend(jbytes)
    out.extend(struct.pack("<II", len(bin_chunk), 0x004E4942))
    out.extend(bin_chunk)
    Path(dst_glb).write_bytes(bytes(out))


def _repack_one_ktx2(d):
    meta = load(d)
    asset_id = meta["id"]
    if meta.get("status") not in {"exported", "in_game"} or not meta.get("export"):
        raise SystemExit(f"{asset_id}: must already be exported before KTX2 repack")
    src_glb = export_path(d)
    if not matches_glb(src_glb, meta["export"]):
        raise SystemExit(f"{asset_id}: exported GLB missing or hash mismatch before repack")
    _ensure_ktx_path()
    gltf = [shutil.which("npx") or "npx", "--no-install", "gltf-transform"]
    web = os.path.join(ROOT, "web")
    with tempfile.TemporaryDirectory(dir=d) as work:
        as_png = os.path.join(work, "png.glb")
        step1 = os.path.join(work, "step1.glb")
        step2 = os.path.join(work, "step2.glb")
        packed = os.path.join(work, "packed.glb")
        _glb_webp_to_png(src_glb, as_png)
        if meta.get("category") == "vegetation":
            # Keep crisp alpha cutout edges on leaves via UASTC baseColor + normal
            subprocess.run(gltf + ["uastc", as_png, step1, "--slots", "{baseColorTexture,normalTexture}"], cwd=web, check=True)
            subprocess.run(gltf + ["etc1s", step1, step2, "--slots", "{metallicRoughnessTexture,occlusionTexture,emissiveTexture}"], cwd=web, check=True)
        else:
            subprocess.run(gltf + ["etc1s", as_png, step1, "--slots", "{baseColorTexture,metallicRoughnessTexture,occlusionTexture,emissiveTexture}"], cwd=web, check=True)
            subprocess.run(gltf + ["uastc", step1, step2, "--slots", "normalTexture"], cwd=web, check=True)
        subprocess.run(gltf + ["meshopt", step2, packed], cwd=web, check=True)
        os.replace(packed, str(src_glb))
    meta["texture_format"] = "ktx2"
    meta["export"]["bytes"] = os.path.getsize(src_glb)
    meta["export"]["sha256"] = sha256(str(src_glb))
    save(d, meta)
    print(f"{asset_id}: repacked to KTX2 ({meta['export']['bytes'] / 1e6:.2f} MB)")


def cmd_repack_ktx2(a):
    targets = []
    if a.all_legacy:
        for d in asset_dirs():
            meta = load(d)
            if meta.get("status") in {"exported", "in_game"} and meta.get("texture_format", "webp") == "webp":
                targets.append(d)
    elif a.ids:
        targets = [find(asset_id) for asset_id in a.ids]
    else:
        raise SystemExit("Specify asset id(s) or --all-legacy")
    for d in targets:
        _repack_one_ktx2(d)
    sync_web()
    print(f"repacked {len(targets)} asset(s) to KTX2 and synced web/public/assets")


def export_path(asset_dir):
    return Path(asset_dir) / "export" / (Path(asset_dir).name + ".glb")


def matches_glb(path, export):
    if not path.is_file() or path.is_symlink():
        return False
    size = path.stat().st_size
    if size < 20 or size != export.get("bytes"):
        return False
    with path.open("rb") as f:
        if struct.unpack("<4sII", f.read(12)) != (b"glTF", 2, size):
            return False
    return sha256(path) == export.get("sha256")


def export_problems(asset_dir, meta):
    export = meta["export"]
    path = export_path(asset_dir)
    problems = []
    if export.get("file") != f"export/{path.name}" or not matches_glb(path, export):
        problems.append("exported GLB is missing or does not match asset.json")
    if export.get("source_sha256") != source_hash(asset_dir):
        problems.append("source changed after export")
    if export.get("sheet_sha256") != (meta.get("review") or {}).get("sheet_sha256"):
        problems.append("export is not tied to the approved review sheet")
    if any(export.get(key) != meta.get(key) for key in ("lod_triangles", "texture_size")):
        problems.append("LOD or texture settings changed after export")
    return problems


def manifest_entry(meta):
    entry = {"id": meta["id"], "category": meta["category"], "title": meta["title"],
             "file": meta["id"] + ".glb", "size_m": meta["size_m"], "bytes": meta["export"]["bytes"]}
    if meta.get("material_class"):
        entry["material_class"] = meta["material_class"]
    return entry


def sync_web():
    """Regenerate the public manifest and flat copies of valid exports."""
    public = Path(WEB_ASSETS)
    public.mkdir(parents=True, exist_ok=True)
    manifest = []
    for d in asset_dirs():
        meta = load(d)
        if meta["status"] not in {"exported", "in_game"}:
            continue
        if not meta.get("export") or gate_problems(d, meta) or export_problems(d, meta):
            raise SystemExit(f"{meta['id']}: cannot sync an invalid export")
        manifest.append(manifest_entry(meta))
        shutil.copyfile(export_path(d), public / manifest[-1]["file"])
    for path in public.glob("*.glb"):
        if path.name not in {entry["file"] for entry in manifest}:
            path.unlink()
    (public / "manifest.json").write_text(json.dumps({"assets": manifest}, indent=2, ensure_ascii=False) + "\n")


def model_paths(root):
    """Find checked-in GLB/glTF files, not package caches or build products."""
    for path, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {"node_modules", "dist", ".git"}]
        for name in files:
            if Path(name).suffix.lower() in {".glb", ".gltf"}:
                yield Path(path) / name


def cmd_check(_):
    errors = []
    known_ids = set()
    published = {}
    canonical = set()
    manifest = []
    public = Path(WEB_ASSETS)
    for d in asset_dirs():
        meta = load(d)
        rel = os.path.relpath(d, ROOT)
        if meta["id"] in known_ids:
            errors.append(f"{rel}: duplicate asset id '{meta['id']}'")
        known_ids.add(meta["id"])
        if meta["id"] != os.path.basename(d) or meta["category"] != os.path.basename(os.path.dirname(d)):
            errors.append(f"{rel}: id/category do not match the folder")
        if meta["status"] not in STATUSES:
            errors.append(f"{rel}: unknown status '{meta['status']}'")
        problems = gate_problems(d, meta) if meta["status"] in SHIPPABLE else []
        export = meta.get("export")
        if meta["status"] in {"exported", "in_game"}:
            if not export:
                problems.append("export receipt is missing")
            elif not problems:
                problems.extend(export_problems(d, meta))
                if not problems:
                    canonical.add(export_path(d))
                    entry = manifest_entry(meta)
                    manifest.append(entry)
                    published[entry["id"]] = public / entry["file"]
                    if not matches_glb(published[entry["id"]], export):
                        problems.append("public GLB is missing or differs from the approved export")
        elif export:
            problems.append("only exported or in_game assets may have an export receipt")
        errors.extend(f"{rel}: {p}" for p in problems)
    for path in set(model_paths(ASSETS)) - canonical | (set(model_paths(Path(ROOT) / "web")) - set(published.values())):
        errors.append(f"{os.path.relpath(path, ROOT)}: not the export of an approved asset")
    try:
        if json.loads((public / "manifest.json").read_text()) != {"assets": manifest}:
            errors.append("public manifest does not match the approved exports")
    except (OSError, ValueError):
        errors.append("public manifest is missing or unreadable")
    if os.path.isfile(PLACEMENTS):
        with open(PLACEMENTS) as f:
            try:
                document = json.load(f)
                errors.extend(f"world/placements.json: {p}" for p in placement_problems(document))
                items = document.get("placements", []) if isinstance(document, dict) else []
                for item in items if isinstance(items, list) else []:
                    asset = item.get("asset") if isinstance(item, dict) else None
                    if not isinstance(asset, str) or asset not in published:
                        errors.append(f"world/placements.json: '{asset}' has not passed the Blender gate")
            except ValueError:
                errors.append("world/placements.json: invalid JSON")
    for e in sorted(errors):
        print("GATE FAIL:", e)
    if errors:
        raise SystemExit(1)
    print(f"gate ok: {len(known_ids)} assets checked")


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
    r = sub.add_parser("repack-ktx2", help="Bestehende WebP-GLBs ohne Neu-Bake nach KTX2 umpacken")
    r.add_argument("ids", nargs="*")
    r.add_argument("--all-legacy", action="store_true")
    r.set_defaults(fn=cmd_repack_ktx2)
    sub.add_parser("swatches", help="Materialmuster mit Cycles/CPU rendern").set_defaults(fn=cmd_swatches)
    args = p.parse_args()
    args.fn(args)


def cmd_swatches(_):
    blender(["--python", os.path.join(BLENDER_TOOLS, "render_swatches.py")])


if __name__ == "__main__":
    main()
