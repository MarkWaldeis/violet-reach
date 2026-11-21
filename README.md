# Violet Reach

Große Fantasy-Welt für den PC-Browser. Jedes Objekt wird einzeln in Blender gebaut und kommt erst ins Spiel, wenn es in Blender geprüft und freigegeben ist.

- Plan mit allen Phasen und Sessions: [PLAN.md](PLAN.md)
- Anleitung für Bau- und Prüf-Sessions: [docs/SESSIONS.md](docs/SESSIONS.md)
- Stilhandbuch und Referenzen: [art/STYLE.md](art/STYLE.md)
- Palette und Materialmuster: [art/palette.png](art/palette.png), [Materialbibliothek](art/materials/README.md)

## Aufbau

```
assets/<kategorie>/<id>/   build.py, asset.json, review/ (Prüfblatt), export/ (.glb)
tools/vr.py                Bauen, Prüfblatt, Bewertung, Export, Tor
tools/blender/             Skripte, die in Blender laufen
web/                       Browser-Laufzeit (Three.js, WebGPU mit WebGL2-Rückfall)
world/                     Höhenkarte und Platzierungen (ab Phase 1)
art/                       Stilhandbuch und Materialbibliothek (ab Phase 1)
```

## Einrichten

Blender 5.3 (`brew install --cask blender`), Node 22 oder neuer und Git LFS.

```sh
git lfs install
git lfs pull
npm --prefix web ci
```

## Ein Objekt von Blender bis in den Browser

```sh
python3 tools/vr.py new crystals mein_kristall      # Ordner mit asset.json und build.py anlegen
python3 tools/vr.py build mein_kristall --builder <bau-session>
python3 tools/vr.py sheet mein_kristall --draft     # schnelle Vorschau: review/draft.jpg
python3 tools/vr.py sheet mein_kristall             # Prüfblatt: review/sheet.jpg
python3 tools/vr.py review mein_kristall --reviewer <andere-session> \
    --scores silhouette=9,form_detail=8,material=9,scale=9,style=8,defects=9
python3 tools/vr.py export mein_kristall            # Detailstufen, gebackene Texturen, .glb
python3 tools/vr.py swatches                        # Materialbibliothek: Cycles/CPU, Kontaktblatt
npm --prefix web run dev                            # http://localhost:5173/?asset=mein_kristall
```

## Das Tor

`vr.py export` und `vr.py check` lassen ein Objekt nur durch, wenn

1. der Status `approved`, `exported` oder `in_game` ist,
2. eine Bewertung von einer anderen Session als der Bau-Session vorliegt und alle sechs Punkte zwischen 8 und 10 liegen,
3. Quelle und Prüfblatt unverändert zur Bewertung passen,
4. beim Veröffentlichen Prüfblatt, Bake-Einstellungen, GLB, Web-Register und Platzierungen zusammenpassen.

`sheet` und `export` bauen die Blender-Quelle neu; eine lokale, veraltete `.blend` fließt nicht ein. Das Tor prüft die dokumentierten Session-IDs und Hashes auf Konsistenz; PR-Prüfer bestätigen zusätzlich die Herkunft der Freigabe.

`python3 tools/vr.py check` und `python3 tools/test_gate.py` laufen bei jedem Pull Request, ebenso der Produktions-Build des Viewers.

## Beweisobjekt

Der [violette Kristallhaufen](assets/crystals/crystal_violet_cluster_a/review/sheet.jpg) ist im Asset-Viewer unter `/?asset=crystal_violet_cluster_a` zu sehen. Mit `&webgl=1` lässt sich der WebGL2-Rückfall gezielt starten. Die GLB enthält drei Detailstufen, gebackene WebP-Texturen und Meshopt-Kompression; KTX2 folgt später.

Der [Gelände-Viewer](web/explore/README.md) ist davon getrennt. Das Beweisobjekt ist noch nicht in der Welt platziert.
