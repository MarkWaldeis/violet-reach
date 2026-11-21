# Weltentwurf — Violet Reach

Reproduzierbar mit Blender 5.3 (eingebautes NumPy, keine Pip-Pakete):

```sh
blender -b --python tools/world/build_world.py
# Schnelle Vorschau: grobe Berechnung, weiterhin runtimekompatible Exportmaße
blender -b --python tools/world/build_world.py -- --draft
python3 tools/world/test_world.py
```

Fester Seed **73129**. 8192 × 8192 m, 4097² Höhenwerte, 2 m Raster.
Blender: X Osten, Y Norden, Z oben. **Runtime: X Osten, Y oben, Z Süden**;
`runtime.z = -blender.y`. JSON-Koordinaten und die Zeilen der Regionskarte
folgen den Runtime-Achsen (oben = Norden).

`terrain/runtime/manifest.json` beschreibt 16 × 16 Kacheln à 512 m.
`<x>_<z>.r16`: je 257² rohe uint16-Werte, little-endian, zeilenweise +Z,
Spalten +X; gemeinsame Randwerte sind identisch.
`h = minHeight + v / 65535 * (maxHeight - minHeight)`.
`terrain/terrain.json` enthält zusätzliche Herkunfts- und Wasserstandsmetadaten.
Keine PNG-Höhenkacheln: das R16-Format ist der vereinbarte Runtime-Handoff.

`regions/regions.png` ist eine 8-Bit-Indexkarte (1025²); IDs, Zentren,
Begrenzungsrechtecke, Charakter und geplante Landmarken stehen in
`regions/regions.json`. Die verrauschten Regionsgrenzen teilen die gesamte Welt:

1. **Lyrenschlucht** — grüne Pfeilerschlucht mit schlanken Felsnadeln.
2. **Aschgrat-Canyon** — tief gewundener Einschnitt im nördlichen Plateau.
3. **Dornengang** — schmaler Pass zwischen steilen Parallelgraten.
4. **Weißwall** — lange helle Steilstufe mit Weißfall-Übergang.
5. **Mondsichel** — sichelförmiger Grat um ein geschütztes Tal.
6. **Spiegelsee** — rundes Seebecken, Wiesen und sanfter zentraler Wanderstart.

`hydrology.json`: Flusslinien `[x,z,water_y,width]`, Seen mit `water_y` und
Uferpolygon `[x,z]`. Uferpolygone liegen am trockenen äußeren Ufersaum, die
sichtbare Wasserfläche etwas innerhalb; Flussmündungen unterbrechen den Saum.
Wasserstände flussabwärts monoton.
Die Wasserfallstelle ist markiert; ausgearbeitete Wasserfall- und Landmarken-
Assets gehören in spätere Phasen. Ebenso sind dunkle Waldflächen hier eine
Materialmaske, noch keine platzierten Bäume.

Das Skript kombiniert domain-verzerrtes fraktales Rauschen, explizite regionale
Formen, zwei konservative Hangtransport-Durchgänge, breite erodierte Täler
und parabelförmige Gerinne. Dies ist künstlerische Makroerosion, keine
vollständige hydrodynamische Simulation. Der Bergrand bleibt innerhalb der
Weltgrenze. `--draft` interpoliert die grobe Vorschau ins gleiche Exportformat;
für die endgültige Welt ohne diesen Schalter bauen.

`review/overview.jpg` (beschriftet), `overview_plain.jpg` und `oblique.jpg`
werden mit **Cycles CPU** erzeugt. `terrain.blend` ist lokal regenerierbar
und nicht versioniert. Die Mesh-Vorschau hat 1025² Vertices; die Runtime-
Höhenfelder behalten volle Auflösung. Die Render zeigen den Weltentwurf,
nicht die spätere Vegetations- und Monumentproduktion.
