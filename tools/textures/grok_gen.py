"""Grok-Bildgenerierung fuer Texturquellen (reproduzierbar ueber prompts.json).

python tools/textures/grok_gen.py grass sand ...   (Namen aus prompts.json)
Je Name ein frischer grok-Prozess in eigenem Temp-cwd; Ergebnis wird als
art/textures/src/<name>_v<N>.jpg (JPEG <= 2 MB) abgelegt.
"""
import json, os, subprocess, sys, tempfile, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "art" / "textures" / "src"
P = json.loads((Path(__file__).parent / "prompts.json").read_text(encoding="utf-8"))
SESS = Path(os.environ["USERPROFILE"]) / ".grok" / "sessions"


def prompt_for(name):
    for grp, common in (("ground", "_common_ground"), ("detail", "_common_detail")):
        if name in P[grp]:
            return P[grp][name] + " " + P[common]
    raise KeyError(name)


def run(name):
    prompt = prompt_for(name)
    full = ("Use your image generation tool (image_gen) to create exactly one square image. "
            "Do not write any files or code. Prompt: " + prompt)
    cwd = Path(tempfile.gettempdir()) / "vr_grok" / f"{name}_{int(time.time()*1000)}"
    cwd.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    r = subprocess.run(["grok", "-p", full, "--always-approve"], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    enc = urllib.parse.quote(str(cwd), safe="")
    sdir = SESS / enc
    imgs = sorted(sdir.glob("*/images/*"), key=lambda p: p.stat().st_mtime) if sdir.exists() else []
    imgs += sorted(cwd.rglob("*.jpg")) + sorted(cwd.rglob("*.png")) + sorted(cwd.rglob("*.webp"))
    if not imgs:
        return f"{name}: KEIN BILD ({time.time()-t0:.0f}s) {r.stdout[-300:]} {r.stderr[-300:]}"
    src = imgs[-1]
    n = 1
    while (SRC / f"{name}_v{n}.jpg").exists():
        n += 1
    out = SRC / f"{name}_v{n}.jpg"
    im = Image.open(src).convert("RGB")
    q = 95
    while True:
        im.save(out, "JPEG", quality=q, optimize=True)
        if out.stat().st_size <= 2_000_000 or q <= 70:
            break
        q -= 5
    with open(src, "rb") as f:
        magic = f.read(4)
    return f"{name}: {out.name} {im.size} src={src.name} magic={magic!r} {time.time()-t0:.0f}s"


if __name__ == "__main__":
    names = sys.argv[1:]
    with ThreadPoolExecutor(max_workers=int(os.environ.get("GROK_PAR", "5"))) as ex:
        for line in ex.map(run, names):
            print(line, flush=True)
