"""Videoband ohne Telefonoberfläche extrahieren (ffmpeg, Pillow).

Aufruf: python references.py <kurzes-video.mp4> <langes-video.mp4> [--force]
Zeitangaben beziehen sich auf die Aufzeichnungen, nicht auf den eingeblendeten Timer.
Vorhandene Bilder werden nicht überschrieben (sonst --force); frames.json wird immer komplett neu geschrieben.
Die Sekunden der Ergänzung sind Suchzeitpunkte (-ss vor -i): ffmpeg liefert das erste Vollbild ab dieser
Zeit; sie liegen 2 ms vor dem per Schärfemaß (Kantenkontrast, Fenster ±0,3 s) gewählten Vollbild.
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
QUALITY = 85
# Ergänzung (Lesezeichen G1–G7, F1–F4, H1–H2 und Detailvorlagen, Zuordnung in bookmark_refs.json).
FRAMES_DETAIL = [
    (1, 3.766, "pillar_gorge_rim"), (1, 4.633, "gorge_aqueduct_far"),
    (1, 5.166, "cliff_bands_aqueduct"), (1, 7.135, "canyon_aqueduct_ribs"),
    (1, 10.37, "canyon_river_walls"), (1, 12.138, "canyon_overview_high"),
    (1, 12.705, "canyon_river_pyramid"), (1, 17.24, "chalk_cliff_layers"),
    (1, 19.208, "crystal_pit_rim"), (1, 19.875, "crystal_pit_close"),
    (1, 23.243, "crescent_spires_meadow"), (1, 25.226, "gas_giant_white_tower"),
    (1, 26.611, "ringed_planet_savanna"), (1, 28.928, "disc_lake_island"),
    (1, 30.713, "shallow_beach_water"), (1, 31.33, "layered_rock_disc"),
    (1, 33.08, "rock_ledge_shore"), (1, 33.731, "beach_bridge_gate"),
    (1, 35.215, "broken_moon_fragments"), (0, 0.431, "acacia_slope_sun"),
    (0, 3.7, "savanna_meadow_depth"), (0, 4.8, "canopy_backlight"),
    (0, 5.016, "under_crown_trunks"), (0, 5.268, "bottle_trees_ring"),
    (0, 5.585, "trunk_bark_close"), (0, 7.151, "tall_grass_ferns"),
    (0, 7.618, "baobab_tree_ferns"), (0, 9.353, "open_meadow_horizon"),
    (0, 10.786, "meadow_structures_horizon"), (0, 12.821, "thick_trunk_canopy"),
    (0, 14.088, "grass_trail"), (0, 14.955, "trunk_ferns_foreground"),
    (0, 16.756, "umbrella_acacia_grove"),
]
QUALITY_DETAIL = 92


def main():
    out = ROOT / "art/reference"
    out.mkdir(parents=True, exist_ok=True)
    records = []
    force = "--force" in sys.argv
    videos = [a for a in sys.argv[1:] if a != "--force"]
    frames = [f + (QUALITY,) for f in FRAMES] + [f + (QUALITY_DETAIL,) for f in FRAMES_DETAIL]
    for i, (video, seconds, subject, quality) in enumerate(frames, 1):
        name = f"ref_{i:02}_{subject}.jpg"
        target = out / name
        x, width = (8, 1154) if video == 0 else (0, 1170)
        if force or not target.exists():
            data = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", str(seconds), "-i", videos[video],
                                            "-frames:v", "1", "-vf", f"crop={width}:659:{x}:812:exact=1", "-f", "image2pipe", "-vcodec", "png", "-"])
            Image.open(io.BytesIO(data)).convert("RGB").save(target, quality=quality, subsampling=0)
        records.append({"file": name, "video": "kurz" if video == 0 else "lang", "seconds": seconds,
                        "crop_xywh": [x, 812, width, 659]})
    (out / "frames.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(records)} Referenzbilder: {out}")


if __name__ == "__main__":
    main()
