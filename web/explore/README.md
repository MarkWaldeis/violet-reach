# Violet Reach · Erkundung

Die Three.js-Laufzeit liegt separat vom Blender-Objektviewer. Standard ist der
**Spiegelsee-Ausschnitt** mit echten Höhenkacheln und freigegebenen Objekten.
`?demo` öffnet die generierte Testlandschaft, `?walk` startet am Wanderstart.
Sie verwendet keine eigene 3D-Engine.

```sh
cd web/explore
npm ci                  # Node.js >= 22.18
npm run dev             # Vite-URL öffnen
npm test
npm run build
npm run preview
```

**Flug und Gehen:** WASD bewegt, Pfeiltasten oder Maus ändern den Blick. Klicken fängt die Maus ein, Esc gibt sie frei; alternativ ziehen. F wechselt zwischen Flug und Landung am aktuellen Standort, Q/E ändern die Flughöhe, Umschalt erhöht das Tempo, R setzt den Blick zum Start zurück.

**Renderer:** Three.js bevorzugt WebGPU und fällt bei fehlender Unterstützung auf WebGL2 zurück. `?webgl` erzwingt WebGL2 für einen Vergleich. Das HUD zeigt das tatsächlich verwendete Backend, die Bildrate, sichtbare Dreiecke, Draw Calls und die geladenen Detailstufen. Die Bildrate hängt von Gerät, Auflösung und Browser ab.

## Weltinhalt und Platzierungen

Vite liefert im Dev-Server und im statischen Build die echte Welt unter
`terrain/`, `hydrology.json`, `slice.json`, `placements.json` und
`assets/<id>.glb`. Der Build prüft `vr.py check` und verweigert platzierte
Assets ohne Status `exported`/`in_game`; Dev-Anfragen prüfen das Tor erneut.
Die R16-Dateien bleiben ausschließlich unter `world/terrain/runtime` in Git.
Slice-Kacheln werden zuerst geladen; die Umgebung bleibt als grober Hintergrund.
Objekte werden ausschließlich innerhalb der Slice-Grenzen platziert.

`?stress=20000` ergänzt deterministisch 20.000 Instanzen des ersten registrierten
Assets auf trockenem Gelände (nur zur Laufzeit, nicht in placements.json).
`?assetDistance=120` setzt die Objekt-Sichtweite in Metern; sonst gilt die
40-fache Modell-Boundingbox-Diagonale. LOD-Wechsel hängen von Modellgröße,
Instanzskalierung, Sichtfeld und Bildschirmhöhe ab, mit 12 % Hysterese.
64-m-Zellen werden alle 100 ms gegen die Betrachter-Frustum geprüft; pro
Asset/LOD/Material gibt es einen gemeinsamen Instanz-Draw. Schatten sind nur
für LOD0/LOD1 freigeschaltet. Kein `THREE.LOD`-Auto-Update in Schattenpässen.

`src/placements.ts` expandiert Singles (`x,z,yaw,scale`, optional `y_offset`)
und Scatter deterministisch. Scatter benötigt `seed` (uint32), `count`, genau
ein `rect: {minX,minZ,maxX,maxZ}` oder `polygon: [[x,z],...]`,
`min_spacing` (m), `max_slope` (Grad), `min_height_above_water`,
`max_height_above_water` (m), `scale: [min,max]`, optional `align_to_slope`.
Abstände gelten pro Scatter-Eintrag. Terrain- und Wasser-Sampler werden vom
Aufrufer geliefert; erst nach Laden der benötigten Kacheln expandieren.
Bei unmöglichen Constraints wird nach höchstens `max(100,count*100)` Versuchen
ein Fehler statt einer stillen Teilmenge geliefert. Normalen bleiben für den
Instanz-Loader erhalten. Instanzhöhe nutzt die vollständigen R16-Samples,
unabhängig vom Gelände-Render-LOD.

## Oberfläche und Atmosphäre

Alle Terrain-LODs teilen dieselben vollständigen Rand-Samples; horizontale
Übergangsdreiecke ersetzen die senkrechten Skirts. Die gesamte 8-km-Welt kann
im Slice-Modus als grober Horizont geladen werden, die Slice-Kacheln zuerst.
Der Gehboden interpoliert auch die Übergangsdreiecke.

**Uferformung im Weltgenerator:** Mäander, Mündungsfächer, flache Nasssäume und
sanfte Böschungen werden in `tools/world/build_world.py` gemeinsam mit den
See-Buchten erzeugt. Stetige, absenkende Profile überlagern sich ohne harte
Gerinnegrenzen. Die frühere Runtime-Uferglättung entfällt; Render-LODs, Gehboden,
Wasseratlas und Platzierungs-Sampler lesen dieselben unveränderten R16-Exporte.

`hydrology.json` liefert Seen und Flussbänder: der ganze Spiegelsee sowie alle
Gewässer im Ausschnitt. Die Seeoberfläche liegt 3 m innerhalb des Uferpolygons;
Terrain über dem Wasserspiegel wird ausgespart. Ein linear gefilterter 4-m-Atlas
aus den geformten vollständigen Höhendaten enthält Bodenhöhe, Wasserstand und
signierte Abstände zu Gewässer- und Seeufer. Er steuert Wassertiefe, Schaum und
nassen Ufersaum. Flussflächen werden pro Fragment an der sichtbaren Seegrenze
abgeschnitten; ihre Normalen gehen vorher weich in die Seenormalen über.
Flussnormalen bewegen sich längs der jeweiligen Fließrichtung. Wasser ist ein
opakes, tiefengefärbtes Material mit analytischer Himmelsreflexion und Fresnel;
keine teuren Bildschirmreflexionen oder zusätzlichen Reflexions-Renderpässe.

Die optionalen `slice.json`-`paths` enthalten jeweils `polyline: [[x,z],...]`
und `width` in Metern. Der Pfad führt vom Wanderstart zur trockenen nördlichen
Uferzunge am Weißfall-Zufluss; das nominelle Flussende liegt bereits im See.
Wegabstände werden analytisch berechnet, damit schmale Wege nicht durch den
4-m-Atlas unterbrochen werden. Weiche Kanten, großflächige Gras-/Boden-/Felsmischungen und nahes Normaldetail
nutzen direkt `art/palette.json`, ebenso Wasser, Himmel und Dunst.
Sonniges Gelbgrün, strohige Trockenwiesen und offene Erde wechseln auf etwa
200-, 50- und 10-m-Skalen. Höhe über Wasser, Nordexposition und die aus vier
Höhenatlas-Nachbarn ermittelte Muldenlage steuern feuchtes Moos. Ab etwa 35–40°
werden helle, höhengeschichtete Kalk-/Strataflächen sichtbar. Direkt am Wasser
folgt auf den dunklen Nasssaum ein sandfarbener Strand; Wege haben erdige Ränder.
Strata entstehen aus geneigtem, großräumig verworfenem 3D-Rauschen statt
periodischen Höhenlinien; vertikale Erosionsspuren unterbrechen die Schichtung.
Deterministisch einmal erzeugte 256²-Detailtexturen liefern Halmbüschel,
Erdkiesel und feinen Sand samt Normalrelief. Sie wiederholen sich weltfest auf
1,54 und gedrehten 0,73 m, mit Mipmaps und 16× anisotroper Filterung; die
Materialgewichte steuern die Mischung, zwischen 30 und 80 m wird ausgeblendet.
`?groundDetail=albedo` bzw. `?groundDetail=normal` zeigt die tatsächlich
abgetasteten, materialgewichteten Texturkanäle für Nahdetail-Diagnosen.

`CSMShadowNode` erzeugt drei weich überblendete 2048²-Kaskaden bis 1100 m.
Der gleiche Node-Pfad funktioniert mit dem WebGPU- und WebGL2-Backend des
WebGPURenderer, ohne `WebGLRenderer`-Material-Patches. Cremefarbene Sonne und
blaugraues Hemisphärenlicht bleiben getrennt von der Paletten-Grundfarbe.
Himmel und langsam ziehende Wolkenbänder sind prozedural im bildfüllenden
Hintergrund, ohne entfernte Himmelskugel oder Nebelkarten. Die Blickrichtung
wird pro Pixel aus der inversen Kameraprojektion rekonstruiert. Höhenabhängiger
Taldunst erhält mehrkilometrige Sichtachsen ohne weltprojizierte Wolkenflecken.
Die Ferne wird cremefarben heller, mit zusätzlichem Streulicht in Sonnenrichtung;
Wolkenbänke erhalten weiche, unregelmäßige Licht- und Schattenseiten.
Ausgabe: sRGB, AgX; kein Bloom.

## Blender-Höhenkarte anbinden

Die Vorschau mit `?terrain=./terrain/manifest.json` öffnen. Bei separatem Hosting muss der Server CORS erlauben. Nach dem Build ist `dist/` ohne Serverlogik statisch auslieferbar.

Manifest v1 enthält `version: 1`, `tilesX`, `tilesZ`, `tileSize` in Metern (mindestens 1 m), `samples` pro Kante (17, 33, 65, 129 oder 257), `originX`, `originZ`, `minHeight` und `maxHeight` in Metern. Optional setzt `spawn: {x,z,yaw}` den Startpunkt; `yaw` ist in Radiant, bei Null blickt die Kamera nach Norden (−Z). Wenn kein Startpunkt angegeben ist, beginnt der Flug in der Mitte der Karte.

Neben dem Manifest liegt für jede Null-basierte Kachel eine Datei `<x>_<z>.r16` mit `samples²` vorzeichenlosen 16-Bit-Werten in Little-Endian. Zeilen laufen nach +Z (Süden), Spalten nach +X (Osten); +Y ist oben. Beide Nachbarn enthalten dieselben Randwerte. `minHeight + sample / 65535 * (maxHeight - minHeight)` ergibt die Höhe. Der Export ist von der Laufzeit unabhängig; Hydrologie wird im Slice-Modus gerendert, Regionsdaten noch nicht.

**Streaming:** Vier parallele Requests; zuerst die nächsten Kacheln. Aktive Kacheln sind durch Radius und Anzahl begrenzt. Höhen werden einmal pro Aufenthalt geladen und bei Bedarf für den Render-LOD ausgedünnt; Geometrie außerhalb der Reichweite wird freigegeben. Der Gehboden folgt den gerenderten Dreiecken, und die Kamera wartet an der Kante, wenn eine benötigte Kachel noch fehlt.
