"""Videoband ohne Telefonoberfläche extrahieren (ffmpeg, Pillow).

Aufruf: python references.py <kurzes-video.mp4> <langes-video.mp4>
Zeitangaben beziehen sich auf die Aufzeichnungen, nicht auf den eingeblendeten Timer.
"""
import json
import io
from pathlib import Path
import subprocess
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
FRAMES = [
    (1, 1, "white_monuments_sky"), (1, 4, "pillar_light"),
    (1, 6, "canyon_cliffs"), (1, 8, "white_ribbed_arches"),
    (1, 12, "river_arch"), (1, 16, "weathered_wall"),
    (1, 18, "violet_crater"), (1, 22, "ribbed_crown"),
    (1, 26, "crescent_grass"), (1, 30, "lake_shore"),
    (1, 34, "floating_bodies"), (0, 2, "forest_path"),
    (0, 7, "forest_ground"), (0, 12, "grass_light"),
]


def main():
    out = ROOT / "art/reference"
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for i, (video, seconds, subject) in enumerate(FRAMES, 1):
        name = f"ref_{i:02}_{subject}.jpg"
        target = out / name
        x, width = (8, 1154) if video == 0 else (0, 1170)
        data = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", str(seconds), "-i", sys.argv[video + 1],
                                        "-frames:v", "1", "-vf", f"crop={width}:659:{x}:812:exact=1", "-f", "image2pipe", "-vcodec", "png", "-"])
        Image.open(io.BytesIO(data)).convert("RGB").save(target, quality=85, subsampling=0)
        records.append({"file": name, "video": "kurz" if video == 0 else "lang", "seconds": seconds,
                        "crop_xywh": [x, 812, width, 659]})
    (out / "frames.json").write_text(json.dumps(records, indent=2) + "\n")
    print(f"{len(records)} Referenzbilder: {out}")


if __name__ == "__main__":
    main()
