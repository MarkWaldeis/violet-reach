# Violet Reach

Große Fantasy-Welt für den PC-Browser. Jedes Objekt wird einzeln in Blender gebaut und kommt erst ins Spiel, wenn es in Blender geprüft und freigegeben ist.

- Plan mit allen Phasen und Sessions: [PLAN.md](PLAN.md)
- Anleitung für Bau- und Prüf-Sessions: [docs/SESSIONS.md](docs/SESSIONS.md)

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

Blender 5.3 (`brew install --cask blender`), Node 22 oder neuer, Git LFS.

```sh
cd web && npm ci
```

## Ein Objekt von Blender bis in den Browser

```sh
python3 tools/vr.py new crystals mein_kristall      # Ordner mit asset.json und build.py anlegen
python3 tools/vr.py build mein_kristall             # build.py in Blender ausführen
python3 tools/vr.py sheet mein_kristall --draft     # schnelle Vorschau: review/draft.jpg
python3 tools/vr.py sheet mein_kristall             # Prüfblatt: review/sheet.jpg
python3 tools/vr.py review mein_kristall --reviewer <andere-session> \
    --scores silhouette=9,form_detail=8,material=9,scale=9,style=8,defects=9
python3 tools/vr.py export mein_kristall            # Detailstufen, gebackene Texturen, .glb
cd web && npm run dev                               # http://localhost:5173/?asset=mein_kristall
```

## Das Tor

`vr.py export` und `vr.py check` lassen ein Objekt nur durch, wenn

1. der Status `approved`, `exported` oder `in_game` ist,
2. eine Bewertung von einer anderen Session als der Bau-Session vorliegt,
3. jeder der sechs Punkte mindestens 8 von 10 hat,
4. `build.py` seit der Bewertung unverändert ist,
5. das Prüfblatt dasselbe ist, das bewertet wurde.

`vr.py check` läuft bei jedem Pull Request. `python3 tools/test_gate.py` prüft diese Regeln selbst.

## Stand dieses Entwurfs

Dieser Zweig ist ein Entwurf des Fundaments (Phase 0) aus der Plan-Session, zur Wiederverwendung durch die Bau-Sessions. Er ist nicht fertig.

Geprüft:

- `vr.py build` und `vr.py sheet` laufen mit Blender 5.3.0 ohne Bildschirm (Cycles auf CPU); das Prüfblatt des ersten Objekts liegt unter `assets/crystals/crystal_violet_cluster_a/review/`.
- Das Tor lehnt nicht freigegebene Objekte und Selbstbewertung ab; `python3 tools/test_gate.py` prüft sieben Regeln.
- `web/` besteht die Typprüfung (`npx tsc --noEmit`).

Nicht geprüft:

- `vr.py export` (Backen, Detailstufen, `.glb`) wurde gestartet, aber vor dem Ende abgebrochen. `tools/blender/export_asset.py` ist deshalb ungetestet.
- Der Viewer in `web/` wurde nie im Browser geöffnet und hat noch kein Objekt geladen.
- Der CI-Ablauf in `.github/workflows/gate.yml` ist nie gelaufen.

Das erste Objekt `crystal_violet_cluster_a` steht auf `blender_review` und hat keine Bewertung; es ist nicht freigegeben. Texturen wären vorerst WebP; KTX2 folgt in Phase 1.
