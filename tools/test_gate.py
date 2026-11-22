#!/usr/bin/env python3
"""Self-test for the Blender gate in vr.py: builds throwaway asset folders and checks each rule."""
import json
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(Path(__file__).resolve().parent / "blender"))
import vr  # noqa: E402
import vrmat  # noqa: E402


def make(root, **overrides):
    d = os.path.join(root, "props", "thing")
    os.makedirs(os.path.join(d, "review"), exist_ok=True)
    with open(os.path.join(d, "build.py"), "w") as f:
        f.write("def build():\n    pass\n")
    with open(os.path.join(d, "review", "sheet.jpg"), "wb") as f:
        f.write(b"sheet")
    meta = {"id": "thing", "category": "props", "status": "approved", "builder": "session-a",
            "title": "Thing", "size_m": [1, 1, 1], "texture_size": 512, "lod_triangles": [200, 80, 20],
            "review": {"reviewer": "session-b", "scores": {c: 9 for c in vr.CRITERIA},
                       "source_sha256": vr.source_hash(d),
                       "sheet_sha256": vr.sha256(os.path.join(d, "review", "sheet.jpg"))}}
    meta.update(overrides)
    with open(os.path.join(d, "review", "sheet.json"), "w") as f:
        json.dump({"source_sha256": vr.source_hash(d),
                   "sheet_sha256": vr.sha256(os.path.join(d, "review", "sheet.jpg"))}, f)
    vr.save(d, meta)
    return d, meta


def expect(name, problems, fragment):
    ok = (not problems) if fragment is None else any(fragment in p for p in problems)
    print(("ok   " if ok else "FAIL ") + name)
    return ok


def check_output():
    out = StringIO()
    with redirect_stdout(out):
        try:
            vr.cmd_check(None)
        except SystemExit as exc:
            assert exc.code == 1
            return out.getvalue().splitlines()
    return []


def shipping_checks(root):
    base = Path(root)
    web = base / "web" / "public" / "assets"
    placements = base / "world" / "placements.json"
    placements.parent.mkdir()
    d, meta = make(base / "assets", status="exported")
    canonical = vr.export_path(d)
    canonical.parent.mkdir()
    chunk = b'{"asset":{"version":"2.0"}} '
    canonical.write_bytes(struct.pack("<4sIII4s", b"glTF", 2, 20 + len(chunk), len(chunk), b"JSON") + chunk)
    meta["export"] = {"file": "export/thing.glb", "bytes": canonical.stat().st_size,
                      "sha256": vr.sha256(canonical), "source_sha256": vr.source_hash(d),
                      "sheet_sha256": meta["review"]["sheet_sha256"], "lod_triangles": meta["lod_triangles"],
                      "texture_size": meta["texture_size"]}
    vr.save(d, meta)

    with patch.multiple(vr, ROOT=base, ASSETS=base / "assets", WEB_ASSETS=web, PLACEMENTS=placements):
        vr.sync_web()
        yield expect("approved export and matching manifest pass", check_output(), None)

        manifest = web / "manifest.json"
        content = manifest.read_text()
        manifest.write_text('{"assets":[{"id":"rogue","file":"rogue.glb"}]}')
        yield expect("invented manifest entry is refused", check_output(), "public manifest")
        manifest.write_text(content)

        runtime = web / "thing.glb"
        runtime.unlink()
        yield expect("missing runtime binary is refused", check_output(), "public GLB")
        runtime.write_bytes(canonical.read_bytes()[:-1] + b"x")
        yield expect("substituted runtime binary is refused", check_output(), "public GLB")

        runtime.write_bytes(canonical.read_bytes())
        rogue = web.parent / "rogue.gltf"
        rogue.touch()
        yield expect("model outside the public asset registry is refused", check_output(), "rogue.gltf")
        rogue.unlink()

        placements.write_text('{"placements":[{"asset":"rogue"}]}')
        yield expect("unregistered placement is refused", check_output(), "placements.json")
        placements.write_text('{"placements":[{"asset":"thing"}]}')
        yield expect("gated placement passes", check_output(), None)

        meta["texture_size"] *= 2
        vr.save(d, meta)
        yield expect("changed bake settings require re-export", check_output(), "texture settings changed")
        del meta["export"]
        vr.save(d, meta)
        yield expect("exported asset without a receipt is refused", check_output(), "export receipt is missing")

        meta["status"] = "blender_review"
        vr.save(d, meta)
        with patch.object(vr, "blender", side_effect=AssertionError("bake should not start")):
            try:
                vr.cmd_export(SimpleNamespace(id="thing"))
            except SystemExit as exc:
                yield expect("unapproved export never invokes Blender", [str(exc)], "has not passed")
            else:
                yield False


def main():
    results = []
    with tempfile.TemporaryDirectory() as root:
        d, _ = make(root)
        original = vr.source_hash(d)
        real_sha256 = vr.sha256

        def changed_library(path):
            return "changed" if str(path).endswith("vrmat.py") else real_sha256(path)

        with patch.object(vr, "sha256", side_effect=changed_library):
            results.append(expect("legacy asset hash ignores vrmat", [] if vr.source_hash(d) == original else ["changed"], None))
        for statement in ("import vrmat", "import vrmat as materials", "from vrmat import get", "from tools.blender import vrmat"):
            Path(d, "build.py").write_text(statement + "\ndef build(): pass\n")
            baseline = vr.source_hash(d)
            with patch.object(vr, "sha256", side_effect=changed_library):
                results.append(expect(statement + " includes library hash", ["changed"] if vr.source_hash(d) != baseline else [], "changed"))
            with patch.object(vr, "sha256", side_effect=lambda p: "changed" if str(p).endswith("palette.json") else real_sha256(p)):
                results.append(expect(statement + " includes palette hash", ["changed"] if vr.source_hash(d) != baseline else [], "changed"))
        Path(d, "build.py").write_text('# import vrmat\nTEXT = "vrmat"\n')
        baseline = vr.source_hash(d)
        with patch.object(vr, "sha256", side_effect=changed_library):
            results.append(expect("comments and strings do not opt into vrmat", [] if vr.source_hash(d) == baseline else ["changed"], None))
        source = Path(root, "props", "parent", "build.py")
        source.parent.mkdir()
        source.write_text("def build(): pass\n")
        Path(d, "build.py").write_text("from assets.props.parent import build as parent\n")
        with patch.object(vr, "ASSETS", root):
            baseline = vr.source_hash(d)
            source.write_text("def build(): return 1\n")
            results.append(expect("imported builder changes dependent review hash",
                                  ["changed"] if vr.source_hash(d) != baseline else [], "changed"))
        for statement, depends in (("from vrcolumn import drum", True), ("# import vrcolumn", False)):
            Path(d, "build.py").write_text(statement + "\n")
            baseline = vr.source_hash(d)
            with patch.object(vr, "sha256", side_effect=lambda p: "changed" if str(p).endswith("vrcolumn.py") else real_sha256(p)):
                results.append(expect(statement + " tracks survey geometry", [] if (vr.source_hash(d) != baseline) == depends else ["incorrect dependency"], None))
    colors = vrmat.load_palette()
    results.append(expect("all material colors match sRGB and linear palette", [] if colors else ["empty"], None))
    results.append(expect("ochre accent remains in palette without an inlay material",
                          [] if "accent_ochre" in colors and "ochre_inlay" not in vrmat.SPECS else ["inconsistent"], None))
    try:
        vrmat.get("ochre_inlay")
    except KeyError:
        results.append(expect("removed inlay material is refused", ["refused"], "refused"))
    else:
        results.append(False)
    try:
        vrmat.get("unknown")
    except KeyError:
        results.append(expect("unknown material name is refused", ["refused"], "refused"))
    else:
        results.append(False)
    for invalid in ({"colors": {}}, {"colors": {"broken": {"srgb_hex": "#FFFFFF", "linear_rgb": [0, 0, 0]}}}):
        with patch.object(Path, "read_text", return_value=json.dumps(invalid)):
            try:
                vrmat.load_palette()
            except ValueError:
                results.append(expect("empty or inconsistent palette is refused", ["refused"], "refused"))
            else:
                results.append(False)
    with tempfile.TemporaryDirectory() as root:
        d, meta = make(root)
        results.append(expect("approved asset passes", vr.gate_problems(d, meta), None))

        d, meta = make(root, status="blender_review")
        results.append(expect("unapproved status is refused", vr.gate_problems(d, meta), "status is"))

        d, meta = make(root, review=None)
        results.append(expect("missing review is refused", vr.gate_problems(d, meta), "no review"))

        d, meta = make(root, builder="session-b")
        results.append(expect("self-review is refused", vr.gate_problems(d, meta), "reviewer is the builder"))

        d, meta = make(root)
        meta["review"]["scores"]["material"] = 7
        results.append(expect("a score below 8 is refused", vr.gate_problems(d, meta), "material=7"))
        meta["review"]["scores"]["material"] = 11
        results.append(expect("a score above 10 is refused", vr.gate_problems(d, meta), "above 10"))

        d, meta = make(root)
        with open(os.path.join(d, "build.py"), "a") as f:
            f.write("# changed after review\n")
        results.append(expect("build.py edited after review is refused", vr.gate_problems(d, meta), "build.py changed"))

        d, meta = make(root)
        with open(os.path.join(d, "review", "sheet.jpg"), "wb") as f:
            f.write(b"another sheet")
        results.append(expect("swapped review sheet is refused", vr.gate_problems(d, meta), "not the sheet"))
        meta["review"]["sheet_sha256"] = vr.sha256(os.path.join(d, "review", "sheet.jpg"))
        results.append(expect("review alone cannot bless a substituted sheet", vr.gate_problems(d, meta), "render receipt"))

    with tempfile.TemporaryDirectory() as root:
        results.extend(shipping_checks(root))
    if not all(results):
        raise SystemExit(1)
    print(f"{len(results)} gate rules hold")


if __name__ == "__main__":
    main()
