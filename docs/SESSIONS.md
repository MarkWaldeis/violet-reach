# Anleitung für Sessions

## Bau-Session

1. Eigener Zweig, nur der eigene Objektordner unter `assets/<kategorie>/<id>/` wird angefasst.
2. `build.py` enthält eine Funktion `build()`. Sie erzeugt Mesh-Objekte und legt jedes mit `vrlib.link_to_source(obj)` in die Sammlung `SOURCE`.
3. Maße in Metern, Z nach oben, Ursprung in der Mitte der Standfläche auf Bodenhöhe. Nichts tiefer als 6 cm unter dem Boden.
4. Feste Zufallszahl (`random.Random(SEED)`), damit `build.py` die Geometrie und Materialien reproduziert. Die Quelle der Phase 0 liegt vollständig in `build.py` und den gemeinsamen Blender-Hilfsfunktionen; zusätzliche Abhängigkeiten brauchen eine Erweiterung des Quell-Hashes.
5. Höchste Detailstufe in der Quelle. Die Dreieckszahl der Quelle ist frei; die Zahlen fürs Spiel stehen in `lod_triangles`.
6. Materialien sind prozedural und undurchsichtig, mit dem Principled BSDF. Was im Prüfblatt zu sehen ist, wird gebacken: Farbe, Normalen, Rauheit, Leuchten, Verdeckung. Transparenz und blickwinkelabhängige Effekte überleben das Backen nicht.
7. Mit `vr.py build <id> --builder <bau-session>` die Urheberschaft erfassen. Mit `vr.py sheet <id> --draft` iterieren, dann `vr.py sheet <id>`.
8. Pull Request mit `build.py`, `asset.json` und `review/`. Die `.blend` wird nicht eingecheckt, sie entsteht aus `build.py`.
9. Cycles läuft auf der CPU. Auf der virtuellen GPU der Devin-Maschine hängt Cycles ohne Fehlermeldung.

## Prüf-Session

1. Nie das eigene Objekt prüfen; `vr.py review` lehnt das ab.
2. `review/sheet.jpg` in voller Größe ansehen, dazu `hero.jpg` und `closeup.jpg`, und mit dem Stilhandbuch und den Referenzbildern vergleichen.
3. Sechs Punkte, je 1 bis 10: `silhouette`, `form_detail`, `material`, `scale`, `style`, `defects` (10 = fehlerfrei).
4. Unter 8 in einem Punkt heißt abgelehnt. Die Mängel konkret in `--notes` schreiben: was, wo, wie beheben. Nach drei abgelehnten Runden entscheidet der Lead über einen Neuansatz.
5. Im Zweifel ablehnen. Das Tor ist der Grund, warum die Welt am Ende gut aussieht.

## Regions-Session

Platzierungen stehen in `world/placements.json` als `{"placements": [{"asset": "<id>", ...}]}`. `vr.py check` lehnt jede Platzierung eines Objekts ab, das das Tor nicht passiert hat.
