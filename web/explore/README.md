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

## Prüfparameter und Prüfwerkzeuge (GRAFIK_PLAN.md 6)

Alle Parameter sind optional; ohne sie verhält sich die Laufzeit wie bisher
(Stufe „high", FOV 57°, HUD sichtbar, laufende Zeit, Spawn mit Anheben).

| Parameter | Wirkung |
|---|---|
| `?cam=x,y,z,yaw,pitch` | Feste Kamerapose als Start, kein Spawn-Lift. `y` absolut in Metern. Die Pose bleibt exakt stehen (auch unter 2,6 m, ohne Bodenklemmung), bis eine Bewegungstaste gedrückt wird; dann übernimmt die Navigation (Gehen, wenn die Pose höchstens 2,6 m über Grund liegt, sonst Flug). |
| `&agl=1` | `y` aus `cam` ist Höhe über Grund. Grund = vollauflösende R16-Höhe (`terrain.fullHeightAt`, Rückfall `heightAt`); unter Wasser ist das der Seegrund. |
| `?fov=<grad>` | Vertikales Sichtfeld, 10–120, Standard 57. |
| `?hud=0` | Blendet alle HUD-/Overlay-Elemente aus, nur die Leinwand bleibt. |
| `?quality=low\|medium\|high\|ultra` | Qualitätsstufe aus `src/quality.ts`, Standard `high` (= bisheriges Verhalten). |
| `?freeze=1` | Alle zeitabhängigen Shader-Effekte (Wolkendrift, Wasserwellen) laufen auf fester Zeit `FROZEN_TIME` = 0 s (`src/world-time.ts`). |

**Winkelkonvention** (wie `src/navigation.ts`, `rotation.order = "YXZ"`): `yaw = 0`
blickt nach Norden (−Z), positives `yaw` dreht nach Westen (gegen den
Uhrzeigersinn von oben), Blickrichtung = (−sin yaw · cos pitch, sin pitch,
−cos yaw · cos pitch). Positives `pitch` blickt nach oben, Grenze ±1,42 rad.
Für ein Ziel in Richtung (dx, dz) gilt `yaw = atan2(−dx, −dz)`. Die Sonne steht bei
yaw 0,735 und 0,557 rad Höhe.

**Qualitätsstufen** (`src/quality.ts`; Gras und Nachbearbeitung kommen später dazu):

| Stufe | pixelRatio max | Schatten | Kaskaden × Kartengröße | Objekt-Sichtweite |
|---|---|---|---|---|
| low | 1 | aus | – | × 0,5 |
| medium | 1 | an | 2 × 1024² | × 0,75 |
| high | 1,5 | an | 3 × 2048² | × 1 |
| ultra | 2 | an | 3 × 4096² | × 1,25 |

Ein explizites `?assetDistance=` hat Vorrang vor dem Sichtweiten-Faktor.

### `window.__vr`

Typisiert in `src/qa-probe.ts` (`VRProbe`), immer vorhanden.

- `ready: boolean` — Pose angewendet, alle aktiven Geländekacheln geladen und in
  der gewünschten Detailstufe gebaut (keine pending/failed Kacheln), Slice-Objekte
  geladen und danach 30 Bilder (`STABLE_FRAMES`) ohne Änderung von Kachel-LODs,
  Instanz-LODs, sichtbaren Chunks oder Pose. `setCamera` setzt `ready` zurück.
- `stats()` — `{backend, adapter: {vendor, architecture, device, description} | null
  (GPUDevice.adapterInfo, nur WebGPU), quality, ready, stableFrames, frame, fps,
  frameTimes[] (ms, letzte 240 Bilder aus rAF-Zeitstempeln), cpuTimes[] (ms
  JavaScript-Zeit je Bild: Update + Render-Aufruf), triangles, drawCalls,
  geometries, textures, textureBytes, textureBytesThree, textureSizes, camera
  {x,y,z,yaw,pitch,agl,fov,mode}, terrain {lods,total,loaded,failed,pending,complete},
  assets, frozen}`.
- `setCamera(x, y, z, yaw, pitch, {agl?})` — setzt die Pose sofort (wie `?cam`).
- `frame()` — Promise, die nach dem nächsten gerenderten Bild mit
  `{now, frameMs, cpuMs, triangles, drawCalls}` erfüllt wird.
- `drive(callback | null)` — Rückruf am Anfang jedes Animationsbilds (vor Update
  und Render) mit rAF-Zeit und dem Datensatz des vorigen Bilds; damit fährt
  `bench.mjs` Strecken in Echtzeit.

**Texturspeicher** (`textureBytes`): Die Laufzeit verfolgt über
`renderer.info.createTexture/destroyTexture` alle tatsächlich hochgeladenen
Texturen (inklusive Schattenkarten und Render-Targets) und summiert
Breite × Höhe × Ebenen (Würfel = 6) × Bytes/Pixel × 4/3, wenn eine Mip-Kette
erzeugt wird. Bytes/Pixel aus Format und Typ (RGB zählt als RGBA, weil die GPU
auffüllt; Tiefe 4 Bytes). Komprimierte Texturen zählen mit der Summe ihrer
Mip-Daten. Nicht enthalten: Bildpuffer/MSAA-Ziele des Backends und Treiber-
Ausrichtung. `textureBytesThree` ist Three.js' eigener Zähler zum Vergleich.

### Lesezeichen und Prüfskripte

`world/bookmarks.json` enthält die 13 Lesezeichen (G1–G7, F1–F4, H1, H2, je mit
Pose, Referenzbildern und Schwerpunkt), die Bildfolgen `walk`/`fly` (je 8 s,
15 Bilder/s) und die Messstrecken `ground` (Bodenweg 400 m mit 10 m/s) und
`flight` (Kreis r = 420 m, 150 m über Grund, 68 m/s). Posen nutzen immer `agl`.

Die Skripte unter `tools/qa/` (Node-ESM, Playwright aus diesem Paket) steuern
das echte Google Chrome sichtbar (`channel: "chrome"`, 1920 × 1080,
deviceScaleFactor 1), damit wirklich die Grafikkarte rendert; es wird kein
Playwright-Browser heruntergeladen. Sie starten bei Bedarf einen eigenen
Vite-Prüfserver auf Port **5198** (`--strictPort`; 5199 gehört der Start-Datei)
und beenden ihn wieder. Für diesen Server gilt `VR_GATE_CACHE_MS=30000`: das
Tor (`vr.py check`) wird höchstens alle 30 s erneut ausgeführt, statt bei jeder
der über 270 Anfragen (sonst lädt der Ausschnitt mehrere Minuten). Ohne die
Variable bleibt die Prüfung je Anfrage wie bisher.

Ein Lauf ist nur gültig mit `backend === "WebGPU"` und einem AMD-Adapter; sonst
endet er mit Exit-Code 3. `--webgl` erzwingt einen ausdrücklich als WebGL2
markierten Lauf. Alle Bilder landen unter
`C:\Users\<Name>\devin-screenshots\violet-reach\<lauf>\`, nie im Repo.

```sh
# alle Vergleichsbilder (+ Bildfolgen als PNG-Serie und MP4)
node tools/qa/capture.mjs [--run <name>] [--only G1,F2] [--quality high] [--seq] [--webgl] [--timeout 180]
# Messbericht bench.json, Abgleich mit web/explore/perf-budget.json (Exit 4 bei Verstoß)
node tools/qa/bench.mjs [--run <name>] [--quality high] [--webgl] [--only ground,flight]
# Probeaufnahmen beliebiger Posen (Lesezeichen einrichten)
node tools/qa/shot.mjs --run <name> G9=x,agl,z,yaw,pitch ...
```

`capture.mjs` öffnet je Lesezeichen eine frische Seite mit
`?hud=0&freeze=1&cam=…&agl=1&fov=…&quality=…`, wartet auf `__vr.ready`
(Zeitlimit mit Zustandsmeldung) und schreibt `<id>.png`, `<id>_compare.jpg`
(links Referenz, rechts Spiel, je 960 × 540), `metrics.json` (aus
`tools/qa/compare.py`: Helligkeit, Kontrast p5–p95, Sättigung, Farbton von
Grünflächen und Himmel für Referenz und Spiel) und `index.json` (Dateien, URLs,
Soll- und Ist-Posen, Zähler). Mit `--seq` werden die Bildfolgen Bild für Bild
gesetzt; je Schritt rendert die Seite 4 Bilder wie ein 60-Hz-Monitor, damit
Nachladen und LOD-Wechsel wie im Spiel sichtbar werden.

`bench.mjs` wärmt je Strecke bis `ready` auf und fährt sie dann in Echtzeit:
Die Pose wird in jedem Bild aus dem rAF-Zeitstempel interpoliert, die Bildzeit
ist also echt. `bench.json` enthält je Strecke Mittel-FPS, 1-%-Low
(1000 / Mittel der schlechtesten 1 % Bildzeiten), längstes Bild, Perzentile,
CPU-Zeit je Bild, Dreiecke und Draw Calls (max/Mittel), Texturspeicher,
Backend/Adapter und Stufe. Bei VSync ist die Bildrate auf die Bildwiederholrate
gedeckelt; die CPU-Zeit zeigt dann die Reserve.
