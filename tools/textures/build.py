"""Alle Texturen aus textures.json bauen und Manifeste schreiben.

python tools/textures/build.py            # alle
python tools/textures/build.py grass moss # Auswahl
"""
import json
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
PUB = ROOT / "web" / "explore" / "public"
CFG = json.loads((HERE / "textures.json").read_text(encoding="utf-8"))


def run(t):
    cmd = [sys.executable, str(HERE / "make_pbr.py")] + shlex.split(t["cmd"])
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return t["name"], r.returncode, (r.stdout + r.stderr).strip()


def manifests():
    for kind in ("ground", "detail"):
        items = {}
        for t in CFG["textures"]:
            if t["kind"] != kind:
                continue
            meta = ROOT / "art" / "textures" / "meta" / f"{kind}_{t['name']}.json"
            if not meta.exists():
                continue
            m = json.loads(meta.read_text(encoding="utf-8"))
            files = sorted(m["files"])
            if kind == "ground":
                files = [f for f in files if f.startswith("1k/")]
            items[t["name"]] = {"tile_m": t["tile_m"], "mean_srgb": m.get("mean"),
                                "palette": t["palette"], "palette_srgb": m.get("palette_hex"),
                                "delta_e": m.get("delta_e"), "roughness_mean": m.get("roughness_mean"),
                                "files": files}
        if kind == "ground":
            doc = {"layout": "1k/<name>_{albedo,normal,orh}.webp",
                   "albedo": "sRGB, RGB", "normal": "linear, RGB = n*0.5+0.5, Tangentenraum OpenGL (+Y oben)",
                   "orh": "linear, R=Verdeckung G=Rauheit B=Hoehe (0..1)"}
        else:
            doc = {"layout": "<klasse>_{normal,rough}.webp, 1024",
                   "normal": "linear, RGB = n*0.5+0.5, Tangentenraum OpenGL (+Y oben)",
                   "rough": "linear, Graustufe (als RGB gespeichert, R lesen)"}
        (PUB / kind / "manifest.json").write_text(json.dumps({"doc": doc, "textures": items}, indent=1, ensure_ascii=False),
                                                  encoding="utf-8")


if __name__ == "__main__":
    want = set(sys.argv[1:])
    todo = [t for t in CFG["textures"] if not want or t["name"] in want]
    with ThreadPoolExecutor(4) as ex:
        for name, rc, out in ex.map(run, todo):
            print(("OK  " if rc == 0 else "ERR ") + out[-600:])
    manifests()
    tot = sum(p.stat().st_size for k in ("ground", "detail") for p in (PUB / k).rglob("*") if p.is_file())
    print(f"public/ground + public/detail: {tot / 1e6:.2f} MB")
