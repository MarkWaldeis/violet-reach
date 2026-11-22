# Violet Reach — Grafik-Plan „Nächstes Level"

Stand 22.11.2026. Auftrag für **eine lokale Devin-Session auf Marks PC**. Dieser Plan gilt für die Grafik der aktuellen Karte; `PLAN.md` (Multi-Session-Plan im GitHub) bleibt unangetastet und ist für diesen Auftrag nicht maßgeblich.

Start der Session mit: *„Lies `GRAFIK_PLAN.md` im Repo `Desktop\Violet Reach` vollständig und führe ihn von Phase 0 an aus."*

---

## 1. Auftrag

Die aktuelle Karte (Welt 8 × 8 km, spielbarer Spiegelsee-Ausschnitt 1 × 1 km) soll im Browser so aussehen wie die beiden Referenzvideos: dichte, realistische Vegetation, klares kräftiges Licht, weiße Monumentalbauten, Kreidefelsen, türkisfarbenes Wasser, Himmelskörper. Dabei muss sie flüssig laufen.

Reihenfolge (von Mark entschieden):

1. **Meilenstein M1:** der 1 × 1 km Spiegelsee-Ausschnitt erreicht die Zielqualität.
2. **Meilenstein M2:** dieselben Bausteine werden auf die ganzen 8 × 8 km ausgerollt.

Die Karte darf umgebaut werden, aber **nie kleiner** als 8 × 8 km und der Ausschnitt nie kleiner als 1 × 1 km.

## 2. Feste Regeln

1. **Meshy-Obergrenze: 2000 Credits insgesamt**, Bilder und 3D zusammen. Startguthaben am 22.11.: 3160. Gezählt wird über das Kostenbuch (Abschnitt 8), nicht über den Kontostand, weil das Monatsguthaben am 22.12.2026 neu aufgefüllt wird.
2. **Immer erst Bild, dann 3D.** Kein `text-to-3d`. Jedes Meshy-Modell entsteht aus einem geprüften, freigestellten Referenzbild (Abschnitt 7).
3. **Referenzbilder für Meshy-3D kommen aus Meshy** (Marks Entscheidung) und kosten 3–9 Credits je Bild. Sie zählen zur Obergrenze.
4. **Texturen, Blatt-Atlanten, Himmelsbilder und alles, was kein 3D-Referenzbild ist, kommen aus Grok** (`grok -p "<prompt>" --always-approve`, ein Prozess je Bild). Das kostet keine Meshy-Credits und darf viel genutzt werden.
5. **Was Blender in guter Qualität kann, baut Blender.** Meshy ist für organische und unregelmäßige Formen da, an denen Skript-Modellierung scheitert (Abschnitt 9).
6. **Alle Meshy-Sachen liegen außerhalb des Repos** in `C:\Users\Mark Waldeis\Desktop\Violet Reach Meshy\` (Abschnitt 7.1). Im Repo liegt nur ein kleines Protokoll je Asset.
7. **Kein Platzhalter bleibt im Spiel.** Jedes neue Objekt geht durch das bestehende Tor (`tools/vr.py`, sechs Kriterien, jeweils mindestens 8 von 10, Prüfer ist nie der Erbauer). Prüfer sind unabhängige Subagenten, die nur Prüfblatt, Referenzbilder und Checkliste bekommen.
8. **Mark hat vorab freigegeben, dass Bilder und Modelle nicht einzeln vorgelegt werden.** Die Session prüft selbst nach den Checklisten und läuft durch. Rückfrage nur bei den Stopp-Bedingungen in Abschnitt 13.
9. **Leistung ist Abnahmekriterium, kein Nachgedanke.** Jedes Arbeitspaket endet mit Messlauf (Abschnitt 6). Wer das Budget reißt, repariert, bevor er weiterbaut.
10. Screenshots und Prüfbilder ausschließlich nach `C:\Users\Mark Waldeis\devin-screenshots\violet-reach\<lauf>\`. Nichts davon ins Repo außer den Prüfblättern unter `assets/**/review/`.
11. Git: eigener Zweig `grafik/next-level` von `main`. Kleine Commits je Arbeitspaket. Push nur auf diesen Zweig, Draft-PR bei M1 und M2. **Kein Merge nach `main` ohne Marks Zustimmung.** Vor jedem Push die LFS-Größe prüfen; über 800 MB anhalten und fragen.
12. Zu Beginn `C:\Users\Mark Waldeis\agent-memory\MEMORY.md` lesen, mindestens die Notizen `blender-52-headless` und `meshy`. Am Ende jedes Meilensteins Erkenntnisse über den Skill `agent-memory-repo` festhalten.

## 3. Ausgangslage (am 22.11. nachgesehen)

**Umgebung:** Windows 11, Ryzen 5 3600, 48 GB RAM, Radeon RX 6600 (8 GB). Blender 5.2 unter `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` (nicht im PATH). Node 26, Python 3.14 (`python`, nicht `python3`), ffmpeg, Grok-CLI, Meshy-CLI 0.8.7 eingeloggt. **Ein Meshy-MCP-Server ist in dieser Devin-Installation nicht eingerichtet**; Meshy läuft über die CLI und den Skill `meshy-3d-generation`. KTX-Werkzeuge, ImageMagick und rembg fehlen.

**Laufzeit** (`web/explore`, Three.js 0.186.1, WebGPU mit WebGL2-Rückfall, TSL-Materialien, rund 1650 Zeilen TypeScript):

- Licht: eine Sonne (Stärke 3) mit 3 Schattenkaskaden bis 1100 m, ein Hemisphärenlicht (1,9), AgX-Tonemapping, Belichtung 1,1. **Keine Nachbearbeitung** (kein AO, Bloom, Kantenglättung über MSAA hinaus, keine Farbkorrektur).
- Himmel: Farbverlauf plus Rauschwolken im Shader. Dunst mischt bis zu 82 % Hazefarbe ein.
- Gelände: R16-Höhenkacheln (2 m Raster, 512-m-Kacheln, 4 Detailstufen). Bodenmaterial rein prozedural aus Palettenfarben plus drei 256²-Detailtexturen, die zwischen 30 und 80 m ausblenden.
- Wasser: opakes Material, analytische Himmelsspiegelung, keine Durchsicht, keine Spiegelung der Szene.
- Objekte: 15 exportierte Assets (3 Bäume, Strauch, Farn, Schilf, Grasbüschel, 3 Kristalle, Tor, Säule, Treppe, Brücke, Ufermodul), je 3 Detailstufen, WebP-Texturen, Meshopt. Bäume 6–11 MB je GLB.
- Im Ausschnitt: 80.098 Instanzen, davon 360 Bäume, 1.148 Sträucher, 2.075 Farne, 12.384 Schilf, 64.120 Grasbüschel. Gras endet bei 20 m, Farn bei 70 m, Strauch bei 260 m.
- Gemessen im Startbild (Flug, 160 m über Grund): WebGPU, 60 FPS, 1,68 Mio. Dreiecke, 65 Draw Calls.

**Bildeindruck des Startbilds** (`devin-screenshots\violet-reach\world-loaded.png`): blass und flau, beiger Dunsthimmel, einfarbige glatte Hänge, wenige helle Bäumchen, winzige Bauten, dunkle flache Wasserfläche, keine Felsen, keine Himmelskörper. Eine Bodenansicht hat dieser Plan nicht geprüft; sie wird in Phase 0 aufgenommen.

**Bekannte Fallen:**

- `tools/vr.py` ruft `blender -b <datei.blend>` auf. Auf diesem PC hängt Blender 5.2 dabei ohne Fehlermeldung. Abhilfe laut Memory: `-b --factory-startup --python x.py` und die Datei im Skript mit `bpy.ops.wm.open_mainfile` öffnen. Außerdem die Umgebungsvariable `BLENDER` setzen.
- Die Höhenkarte wurde mit Blender 5.3 auf einer anderen Maschine erzeugt (`world/terrain/terrain.json`). Vor jeder Geländeänderung erst unverändert neu bauen und mit den eingecheckten R16-Dateien vergleichen (Phase 2).
- Cycles lief bisher nur auf der CPU. Ob HIP auf der RX 6600 stabil bakt, ist ungeprüft; nur nach einem bestandenen Vergleichs-Bake umstellen.
- AgX entsättigt. Der Ziel-Look ist kräftiger; die Wahl des Tonemappings wird in Phase 1 gemessen statt angenommen.
- Meshy bewahrt Task-Dateien nur 3 Tage auf. Jede Datei sofort herunterladen.

## 4. Zielbild aus den Videos

Quellen: `C:\Users\Mark Waldeis\Downloads\ScreenRecording_11-21-2026 15-29-47_1.mp4` (38 s, Überflug) und `…15-30-40_1.mp4` (18 s, Bodenfahrt). Spielbild liegt im Ausschnitt `crop=1170:659:0:812`. 14 Standbilder liegen schon unter `art/reference/`. Die Videos sind Stilvorlage; Karten, Fahrzeuge, Schriftzüge und genaue Bauformen werden nicht kopiert (`art/STYLE.md`).

**Bodenfahrt, wichtigste Vorlage für M1:**

- Kniehohes dichtes Gras bis zum Horizont, dazwischen Farne und großblättrige Bodenpflanzen. Kein freier Boden außer auf Wegen.
- Schirmakazien mit flachen dunklen Kronen, dicke flaschenförmige Stämme, dichte Laubbäume mit fast schwarzen Schattenseiten.
- Harte Sonne mit Gegenlicht, Lichtstrahlen durch Kronen, tiefe Schlagschatten, kräftiges Gelbgrün in der Sonne.
- Monumente und schwebende Körper stehen als helle Silhouetten im Dunst hinter den Bäumen.

**Überflug:**

- Blauer Himmel mit plastischen Haufenwolken, gestreifter Planet, Monde mit aufgebrochener Schale, schwebende elfenbeinfarbene Körper mit violettem Band.
- Kreideweiße Felswände mit waagrechten Schichten und Grasbändern, tiefe Schluchten, Felsnadeln, ein Sandsteinbogen, ein Viadukt.
- Riesige weiße Rippenbögen und Kronen (Höhe über 100 m), Tor mit Lichtsäule, Ruinen.
- Violette Kristallgrube mit Erdrand, violette Splitter in der Wiese.
- Türkisfarbener See mit hellem Sandstrand, Inselmonument, sichtbarem Grund im Flachwasser.

**Ehrliche Grenze:** Die Videos stammen sichtlich aus einer nativen High-End-Engine. Im Browser gibt es weder deren Geometrie-Streaming noch Echtzeit-Global-Illumination. Erreichbar ist derselbe Gesamteindruck in denselben Kameralagen, mit gebackener Verdeckung, Bildschirmraum-Effekten, dichter Vegetation und guten Einzelobjekten. Wo das Ergebnis sichtbar hinter der Vorlage bleibt, steht das im Abschlussbericht mit Bild und Grund.

## 5. Die größten Lücken, nach Wirkung geordnet

| # | Lücke | Hebel | Phase |
|---|---|---|---|
| 1 | Flaues Licht, Dunst überall, kein Kontrast | Sonne, Himmel, Umgebungslicht, Tonemapping, Nachbearbeitung | 1 |
| 2 | Boden ist eine Farbfläche | PBR-Bodenschichten, Makrokarte für die ganze Welt, Fels an Steilhängen | 2 |
| 3 | Vegetation dünn und endet nach 20 m | Gras als Laufzeitsystem, Bodenpflanzen, neue Bäume, Fernbilder (Impostor), Wind | 4 |
| 4 | Keine Felsen und Klippen | Klippen- und Felsbausatz aus Meshy, an Steilhänge gesetzt | 5 |
| 5 | Bauten zu klein und zu wenige | Riesenrippen aus Blender, Hero-Monumente und Ruinen aus Meshy | 5–6 |
| 6 | Wasser flach und dunkel | Tiefenfarbe mit Durchsicht, Wellen-Normalen, Spiegelung, Schaum | 2 |
| 7 | Leerer Himmel | Planet, Monde, schwebende Körper, Wolkenbilder aus Blender | 1 und 5 |
| 8 | Keine Leistungsreserven für das alles | Stufen, KTX2, Kachel-Streaming für Platzierungen, Messlauf | 0, 3, 7, 8 |

## 6. Arbeitsschleife

Jedes Arbeitspaket (AP) läuft so ab. Kein AP gilt ohne Schritt 5 als fertig.

1. **Bauen.** Eine klar begrenzte Änderung.
2. **Aufnehmen.** `tools/qa/capture.mjs` rendert alle Lesezeichen (Abschnitt 6.1) in den Ordner des Laufs und baut je Lesezeichen ein Vergleichsbild: links Referenzbild, rechts Spiel.
3. **Messen.** `tools/qa/bench.mjs` fährt die zwei festen Strecken (Bodenweg, Überflug) und schreibt Bildzeiten, Dreiecke, Draw Calls und Speicher als JSON. Abgleich gegen `web/explore/perf-budget.json`.
4. **Kritik.** Drei unabhängige Prüfer-Subagenten bewerten die Vergleichsbilder nach der Rubrik (6.2). Sie kennen weder frühere Noten noch die Begründung des Erbauers. Die Session selbst bewertet nicht mit.
5. **Entscheiden.** Mängelliste nach Wirkung sortieren. Die obersten Punkte beheben und zurück zu Schritt 2. Fällt ein Lesezeichen gegenüber dem letzten angenommenen Stand um mehr als 0,5 Punkte, wird das AP repariert oder per Git zurückgenommen.
6. **Festhalten.** Commit, Eintrag in `docs/grafik/STATE.md` (aktuelles AP, Noten je Lesezeichen, Messwerte, Credits, offene Mängel, nächster Schritt). Diese Datei muss ausreichen, damit eine neue Session nahtlos weitermachen kann.

Höchstens 6 Runden je AP. Danach den besten Stand behalten, die Restmängel in `STATE.md` notieren und weitergehen; sie kommen in der Schlussrunde der Phase wieder auf den Tisch.

### 6.1 Lesezeichen

Feste Kamerapositionen in `world/bookmarks.json`, jeweils mit zugeordnetem Referenzbild und Schwerpunkt. Die genauen Koordinaten legt Phase 0 fest; bekannte Punkte im Ausschnitt: Flugstart (200, 1200), Wanderstart (350, 1360), Tor (522, 1510), Brücke (480, 1504), Säulen (528, 1445), Kristallnadel (424, 1412), Treppe (600, 1500).

| Kürzel | Lage | Vorlage | Schwerpunkt |
|---|---|---|---|
| G1 | Wanderstart, Blick den Weg entlang zum See | Bodenvideo 0:02 | Gras, Weg, Tiefe |
| G2 | Im Hain unter einer Krone, Blick zur Sonne | Bodenvideo 0:05 | Gegenlicht, Strahlen, Laub |
| G3 | Offene Wiese, Bauten am Horizont | Bodenvideo 0:09 | Grasdichte, Fernsilhouetten |
| G4 | Neben dickem Stamm, Farne im Vordergrund | Bodenvideo 0:15 | Rinde, Bodenpflanzen aus der Nähe |
| G5 | Am Ufer, Strand, Wasser, Brücke | Flugvideo 0:33 | Wasser, Sand, nasser Saum |
| G6 | 3 m vor einem Monumentsockel | `ref_06` | Oberfläche aus der Nähe |
| G7 | Am Fuß einer Felswand | `ref_02`, `ref_03` | Fels, Übergang zum Boden |
| F1 | Flugstart, heutiges Startbild | Flugvideo 0:30 | Gesamteindruck |
| F2 | 30 m über dem Ufer zum Inselmonument | Flugvideo 0:28 | See, Insel, Himmel |
| F3 | Knapp über Baumkronen auf die Rippenkrone zu | Flugvideo 0:22 | Wald von oben, Größenmaßstab |
| F4 | Entlang der Felsbänder am Rücken | Flugvideo 0:06 | Klippen, Schichten |
| H1 | 350 m hoch über dem ganzen Ausschnitt | `ref_09` | Bodenmuster, Baumverteilung |
| H2 | 350 m hoch, Blick aus dem Ausschnitt in die Welt | Flugvideo 0:01 | Fernsicht, Horizont |

Für M2 kommen je Region zwei Lesezeichen dazu (eine Flug-, eine Bodenlage). Zusätzlich je Lauf zwei 8-Sekunden-Bildfolgen (Gehen, Fliegen) für die Prüfung auf Flimmern und sichtbares Umschalten der Detailstufen.

Dafür nötig (Phase 0): URL-Parameter `?cam=x,y,z,yaw,pitch`, `?fov=`, `?hud=0`, `?quality=`, `?freeze=1` (Wind und Wolken auf festem Zeitpunkt) und ein Prüf-Objekt `window.__vr` mit `ready` (alle Kacheln und Objekte geladen, Bild stabil), `stats()` und `setCamera()`.

### 6.2 Rubrik der Prüfer

Je Lesezeichen 1–10 in acht Punkten: Licht und Atmosphäre · Boden · Vegetation (Dichte und Qualität) · Fels und Bauten · Wasser · Himmel · Maßstab und Bildaufbau · technische Fehler (Flimmern, Kacheln sichtbar, schwebende Objekte, harte Kanten, sichtbares Umschalten). Punkte, die im Bild nicht vorkommen, bleiben leer. Dazu je Prüfer die fünf schwersten Mängel mit Ort im Bild und vermuteter Ursache.

10 heißt: vom Referenzbild nicht zu unterscheiden. 8 heißt: gleicher Eindruck, Unterschiede erst beim genauen Hinsehen. 5 heißt: erkennbar dasselbe Motiv, aber klar schwächer.

**Abnahme eines Meilensteins:** Median der drei Prüfer in jedem Punkt auf jedem Lesezeichen mindestens 8, kein Mangel der Art „zerstört den Eindruck", Leistungsbudget eingehalten.

Als Gegenprobe zu den Noten misst `capture.mjs` je Bildpaar Helligkeit, Kontrast (5.–95. Perzentil), Farbsättigung, Farbton der Grünflächen und des Himmels. Die Werte sind Hinweis, kein Ziel.

## 7. Meshy-Pipeline

Vor dem ersten Aufruf den Skill `meshy-3d-generation` laden und dessen Regeln befolgen (`--format json --no-update-check` an jedem Befehl, `create --async` und danach `wait`, nie doppelt abschicken, Flags mit `--help` prüfen). Abweichung vom Skill: keine Einzelfreigabe durch Mark (Regel 8).

### 7.1 Ordner außerhalb des Repos

```
C:\Users\Mark Waldeis\Desktop\Violet Reach Meshy\
  README.md            Aufbau und Regeln dieses Ordners
  ledger.csv           Kostenbuch, eine Zeile je bezahltem Aufruf
  queue.json           alle geplanten Assets mit Klasse, Status, Versuchszähler
  <asset_id>\
    brief.md           Zweck, Maße in Metern, Zieldreiecke, Referenzbilder, alle Prompt-Fassungen
    image\v1.png …     jede Bildfassung samt Meshy-Sidecar
    image\chosen.png   das freigegebene, freigestellte Bild (RGBA)
    image_qa.json      Checkliste mit Ergebnis je Fassung
    model\raw.glb      Rohmodell von Meshy, unverändert, plus Sidecar und Vorschaubild
    model_qa\          Rundum-Blatt aus Blender, qa.json
```

Im Repo je Asset `assets/<kategorie>/<id>/meshy.json`: Prompts, Modellwahl, Task-IDs, SHA-256 von `chosen.png` und `raw.glb`, Credits. `tools/vr.py` nimmt `meshy.json` in den Quell-Hash auf. `build.py` lädt `raw.glb` über einen neuen Helfer `tools/blender/vrmeshy.py` aus dem Bibliotheksordner (Pfad aus der Umgebungsvariable `VR_MESHY_DIR`) und bricht ab, wenn der Hash nicht stimmt. So bleibt die Prüfung im CI ohne die großen Dateien möglich.

### 7.2 Schritt 1: Referenzbild

Vorlage (Flags vor Gebrauch mit `meshy text-to-image create --help` abgleichen):

```
meshy text-to-image create --ai-model nano-banana-2-lite --prompt "<PROMPT>" --aspect-ratio 1:1 --remove-background true --operation-id <id>-img-v<n> --async --format json --no-update-check
```

Prompt-Gerüst: *Gegenstand, Material, Zustand, Größenhinweis* · single isolated object, whole object visible, nothing cropped · three-quarter view from slightly above · centered, fills about 80 % of the frame · flat even overcast lighting, no cast shadows, no rim light · no ground plane, plain background · photorealistic, matte surface, fine surface detail · no text, no people.

Besonderheiten:

- **Bäume immer ohne Laub** anfordern (Stamm mit Hauptästen). Bild-zu-3D macht aus Laub Klumpen; die Krone baut Blender (Phase 4).
- **Felswände** als frei stehender Felsblock mit einer Schauseite anfordern, nicht als Landschaft.
- Farben an `art/palette.json` anlehnen (Kreideweiß, Elfenbein, Sandstein, gedecktes Violett), kein Glanz.
- Gleichmäßiges Licht ist Pflicht: Das Standardmodell von Meshy entfernt eingebackenes Licht nicht.
- Für Objekte, deren Rückseite zählt (Inselmonument, Sandsteinbogen), Mehransicht mit `--generate-multi-view true` und danach `multi-image-to-3d`.
- Kleine Korrekturen an einem fast passenden Bild über `image-to-image` mit `--input-task-id`, statt neu zu würfeln.

Stufen der Bildmodelle: Standard `nano-banana-2-lite` (3 Credits). Fällt ein Asset zweimal durch, einmal `nano-banana-2` (6) oder `gpt-image-2-5-flare` (9). Welche Stufe der Standard wird, klärt die Kalibrierung in Phase 3.

**Checkliste Bild** (die Session sieht jedes Bild selbst an; bei Klasse A zusätzlich ein Prüfer-Subagent):

1. Genau ein Objekt, vollständig, nichts angeschnitten, mindestens 8 % Rand.
2. Alphakanal sauber: kein Hintergrundrest, kein heller Saum, keine Löcher im Objekt (per Skript prüfen: Anteil halbtransparenter Pixel, Randpixel deckend gleich null).
3. Kein Schlagschatten, kein Bodenstück, keine harte Lichtkante, keine Unschärfe.
4. Form in 3D glaubwürdig: keine frei schwebenden Teile, keine papierdünnen Flächen, Tiefe erkennbar.
5. Material und Farbe passen zu Stilhandbuch und Palette.
6. Proportionen passen zu den Maßen im `brief.md`.
7. Kein Text, kein Wasserzeichen, kein Laub an Bäumen.

Höchstens 3 Bildfassungen je Asset. Danach Prompt grundlegend ändern (zählt als neuer Versuch im Kostenbuch) oder das Asset an Blender abgeben.

### 7.3 Schritt 2: 3D aus dem Bild

Eingabe ist immer die lokale Datei `image\chosen.png` (`--image-url "<pfad>"`), damit das geprüfte Bild und das verwendete Bild sicher dasselbe sind.

| Klasse | Wofür | Aufruf | Credits |
|---|---|---|---|
| A | Hero-Objekte, die man aus der Nähe und als Silhouette sieht | `image-to-3d create --model-type standard --should-texture true --texture-model meshy-7 --enable-pbr true --texture-resolution 4k --target-formats glb` | 30 |
| A-Mehransicht | Hero-Objekte mit wichtiger Rückseite | `multi-image-to-3d create` mit denselben Textur-Flags | 30 |
| B | Requisiten, die vielfach gesetzt werden (Stämme, Brocken, Trümmer, Kristalle) | `image-to-3d create --model-type smart-topology --target-polycount 30000 --should-texture true --texture-model meshy-7 --enable-pbr true --texture-resolution 4k --target-formats glb` | 15 |

Nicht verwenden: `--geometry-resolution` (Aufpreis), `remesh`, `convert`, `text-to-3d`, Rigging. Detailstufen und Formatwechsel macht Blender kostenlos. `retexture` (10 Credits) ist nur erlaubt, wenn die Form gut und nur die Textur schlecht ist.

Nach jedem bezahlten Aufruf: `wait`, sofort `raw.glb` und Vorschaubild in den Bibliotheksordner laden, `consumed_credits` und `meshy balance` ins Kostenbuch. Zeitüberschreitung heißt weiter warten, nie neu abschicken. Fehlgeschlagene Tasks werden erstattet; im Kostenbuch als 0 führen.

### 7.4 Schritt 3: Prüfung des Rohmodells in Blender

Skript `tools/meshy/inspect_raw.py` (headless) importiert `raw.glb` und erzeugt ein Rundum-Blatt: 8 Ansichten, Drahtgitter, nur Grundfarbe, 1,8-m-Maßfigur. Automatische Prüfungen:

- Tiefe mindestens 35 % der Breite (fängt flache Scheiben ab), Seitenverhältnis passt zum Brief.
- Zahl loser Teile, Löcher, nicht-mannigfaltiger Kanten, Dreieckszahl (`meshy inspect faces`).
- Eingebackenes Licht: Helligkeitsgefälle der Grundfarbe zwischen Ober- und Unterseite sowie zwischen den vier Seiten.
- Texturgröße und Vorhandensein von Normalen- und Rauheitskarte.

Ein Prüfer-Subagent bewertet das Blatt gegen Referenzbilder und Brief. Urteil:

| Urteil | Folge |
|---|---|
| gut | weiter zu 7.5 |
| in Blender behebbar | weiter zu 7.5 mit Mängelliste (Sockel abschneiden, Teile entfernen, Farbe angleichen, Licht herausrechnen) |
| Form gut, Textur schlecht | `retexture` mit Stilbild oder Textprompt, einmal |
| Form schlecht | neues oder korrigiertes Bild, dann neues 3D. **Nie dasselbe Bild zweimal bezahlen.** Höchstens eine Neu-Generierung je Asset; danach an Blender abgeben oder streichen |

### 7.5 Schritt 4: Aufbereitung in Blender und Export

`assets/<kategorie>/<id>/build.py` lädt das Rohmodell und macht daraus die Quelle:

- Auf Meter laut Brief skalieren, Ursprung mittig auf die Standfläche, Ausrichtung festlegen, Sockelreste und Schwebeteile entfernen, Normalen richten.
- Grundfarbe an die Palette angleichen (Farbton und Sättigung gegen die Palettenwerte messen), eingebackenes Licht herausrechnen, Rauheit bei Stein nicht unter 0,5, Metall 0.
- Eingrabe-Rand am Fuß ergänzen, damit das Objekt auf schrägem Boden ohne Spalt steht.
- Bäume: Blender setzt die Krone aus Astbüschel-Karten auf die Astenden (Phase 4).
- Klasse B: Detailstufe 0 ist das aufgeräumte Meshy-Netz mit seinen eigenen UVs und Texturen (verkleinert auf das Texturbudget); weitere Stufen durch Reduktion mit erhaltenen UV-Nähten.
- Klasse A: Detailstufe 0 wird reduziert und bekommt Grundfarbe, Normalen, Rauheit vom Rohmodell gebacken (bestehender Weg in `export_asset.py`).
- Für alle: Verdeckung backen, Prüfblatt rendern, Tor durchlaufen, Export.

Jedes Asset bekommt in `asset.json` eine Materialklasse (`stone_white`, `rock_chalk`, `sandstone`, `bark`, `crystal`, `foliage`). Die Laufzeit legt je Klasse im Nahbereich eine kachelnde Detailtextur über (Normalen und Rauheit, weltfest, dreiseitig projiziert). Ohne das wirkt ein 40-m-Objekt mit 4K-Textur aus der Nähe unscharf.

## 8. Budget und Kostenbuch

| Posten | Credits |
|---|---|
| Pilot und Kalibrierung (Phase 3) | 150 |
| Referenzbilder für den Ausschnitt (36 Assets, im Schnitt 2 Fassungen) | 280 |
| 3D Klasse A für den Ausschnitt (14 × 30) | 420 |
| 3D Klasse B für den Ausschnitt (22 × 15) | 330 |
| Ausrollen: 8 Hero-Objekte für die Regionen samt Bildern | 300 |
| Nachbesserung: Retexture, Neu-Generierung, Mehransicht | 320 |
| Eiserne Reserve, nur nach Rückfrage bei Mark | 200 |
| **Summe** | **2000** |

`ledger.csv`: Datum, Asset, Schritt, Meshy-Ressource, Task-ID, Modell, erwartete Credits, tatsächliche Credits, Kontostand danach, Urteil. Vor jedem bezahlten Aufruf rechnet `tools/meshy/budget.py`: bisherige Summe plus Schätzung muss unter der Posten-Grenze und unter 1800 liegen, sonst Abbruch. Weicht ein tatsächlicher Preis von der Preisliste (`https://docs.meshy.ai/api/pricing.md`, gelesen am 22.11.2026) ab, sofort die Tabelle neu rechnen und notieren.

Geht ein Posten zur Neige, wird die Asset-Liste gekürzt (von unten in Abschnitt 9), nicht die Reserve angezapft.

## 9. Wer baut was

### 9.1 Meshy (36 Assets für den Ausschnitt)

| Familie | Assets | Klasse |
|---|---|---|
| Stämme ohne Laub | `trunk_acacia_a` (Schirmform, 9–12 m), `trunk_acacia_b` (mehrstämmig, 6–8 m), `trunk_baobab_a` (Flaschenstamm, 10–14 m), `trunk_broadleaf_d` (knorrig gegabelt, 12–16 m), `snag_dead_a`, `log_fallen_a`, `stump_roots_a` | B |
| Felsbrocken | `boulder_chalk_a/b/c` (1–4 m), `rock_slab_a`, `scree_pile_a`, `shore_rocks_wet_a` | B |
| Klippen | `cliff_chalk_wall_a/b` (je rund 40 × 25 m), `cliff_chalk_corner_a`, `rock_pillar_chalk_a` (35 m), `arch_sandstone_a` (45 m, Mehransicht) | A |
| Monumente | `monument_split_disc_a` (Insel, 40 m, Mehransicht), `ruin_wall_a`, `ruin_wall_b` (mit Bogenfenster), `monument_obelisk_a`, `pavilion_shore_a`, `rib_base_ornament_a` (Sockel der Blender-Rippen) | A |
| Trümmer | `column_broken_a`, `ruin_blocks_a/b`, `capital_fallen_a`, `stair_fragment_a` | B |
| Kristall | `crystal_giant_a` (8–12 m), `crystal_shards_a` | B |
| Energie | `energy_core_a` (seltene Landmarke, 10–35 m) | A |
| Himmel | `skyship_pod_a` (eigener Entwurf, elfenbein mit violettem Band, 60 m), `floating_rock_a` | A |
| Himmel | `skyship_pod_b`, `floating_rock_b` | B |

Die acht Hero-Objekte für M2 legt die Session nach der M1-Auswertung fest, eines bis zwei je Region laut `world/regions/regions.json` (zum Beispiel Wächtertor im Dornengang, Wasserfalltor am Weißwall, Grat-Tempel an der Mondsichel, Pfeilertor in der Lyrenschlucht).

### 9.2 Blender, ohne Credits

- **Riesenrippen und Rippenkronen** (30–120 m), Viadukt, Rampen, Plattformen: glatte, große, regelmäßige Formen per Skript; Oberfläche aus kachelnden Grok-Texturen plus gebackener Kantenabnutzung.
- **Alle Baumkronen**, Sträucher, Farne, großblättrige Bodenpflanzen, Blumen, Schilf: Karten aus Blatt- und Astbüschel-Atlanten.
- **Fernbilder (Impostor)** je Baumart: aus 8 × 8 Richtungen gerenderte Atlanten mit Farbe, Normalen und Tiefe.
- **Wolkenbilder:** volumetrische Haufenwolken in Cycles rendern, als Atlas mit Farbe und Normalen für die Beleuchtung zur Laufzeit.
- **Planet und Monde:** Kugeln mit Grok-Texturen, als Himmelsebene.
- **Wasser-Normalen** und Schaumkarte: Ocean-Modifier, kachelnd gebacken.
- **Geländeumbau**, Kristallgrube mit Erdrand, Wege, Uferkanten, Lichtsäule.
- Alle Detailstufen, alle Bakes, alle Prüfblätter.

Die 15 vorhandenen Assets werden in Phase 5 gegen die neue Messlatte geprüft. Wer in G4, G6 oder F3 unter 8 liegt, wird überarbeitet oder ersetzt (die drei Laubbäume voraussichtlich durch die neuen Arten).

### 9.3 Grok, ohne Credits

Kachelnde Bodentexturen (Gras, Trockengras, Erde, Sand, nasser Sand, Kiesweg, Kreidefels, Schichtfels, Moos), Detailtexturen je Materialklasse, Blatt- und Astbüschel-Atlanten auf einfarbigem Hintergrund, Planeten- und Mondoberflächen. Jedes Bild ansehen; Kachelbarkeit mit einem 3 × 3-Testbild prüfen; Fehlversuche löschen und neu erzeugen. Aus der Farbkarte leitet `tools/textures/make_pbr.py` Höhe, Normalen und Rauheit ab und rechnet großflächige Helligkeitsunterschiede heraus.

## 10. Phasen

### Phase 0 — Fundament und Ausgangsmessung

1. Zweig anlegen, `STATE.md` anlegen, Memory lesen.
2. Werkzeuge lauffähig machen: `BLENDER` setzen, den Blender-Hänger in `vr.py` umgehen, `python tools/vr.py check`, `python tools/test_gate.py`, `npm test` und `npm run build` in `web/explore` grün. KTX-Software installieren (`winget`), Aufruf über `gltf-transform` prüfen.
3. Prüf-Parameter und `window.__vr` in die Laufzeit einbauen (6.1). `tools/qa/capture.mjs` und `tools/qa/bench.mjs` mit Playwright und echtem Chrome schreiben. Jeder Lauf prüft, dass wirklich WebGPU auf der RX 6600 läuft; sonst ist die Messung ungültig. Prüfserver auf Port 5198 (5199 gehört der Start-Datei).
4. Referenzbilder: zu den 14 vorhandenen rund 30 weitere Standbilder in voller Auflösung aus beiden Videos ziehen, den Lesezeichen zuordnen.
5. Lesezeichen festlegen, Ausgangsstand aufnehmen, messen, von den Prüfern benoten lassen. Diese Noten sind die Nulllinie.
6. Bibliotheksordner, `ledger.csv`, `queue.json`, `budget.py` anlegen. `meshy auth status` und `meshy balance` prüfen.

Fertig, wenn: ein Befehl erzeugt alle Vergleichsbilder, ein Befehl erzeugt den Messbericht, Nulllinie steht in `STATE.md`.

### Phase 1 — Licht, Himmel, Bildaufbereitung (keine neuen Objekte)

Vorher in `web/explore/node_modules/three/examples/jsm/tsl/display/` nachsehen, was diese Three-Version mitbringt (vorhanden sind unter anderem `GTAONode`, `BloomNode`, `GodraysNode`, `SSRNode`, `SSGINode`, `SSSNode`, `TRAANode`, `FXAANode`, `Lut3DNode`, `FSR1Node`, `TAAUNode`), und die passenden WebGPU-Beispiele als Vorlage nehmen.

1. **Himmel:** physikalisch begründeter Tagesverlauf (kräftiges Blau im Zenit, heller Horizont), Sonnenscheibe, zwei Wolkenebenen aus den Blender-Wolkenbildern (ferner Wolkensaum, darüber rund 60–150 große Einzelwolken mit Beleuchtung aus Sonnenrichtung). Planet und Monde als Himmelsebene hinter den Wolken.
2. **Umgebungslicht aus dem eigenen Himmel:** einmal beim Start eine Umgebungskarte aus der Himmelsszene erzeugen und für diffuses und spiegelndes Licht nutzen; das Hemisphärenlicht entfällt oder wird zum schwachen Zusatz.
3. **Sonne und Schatten:** wärmere, stärkere Sonne; 4 Kaskaden mit enger erster Kaskade für Kontaktschatten; Schattenstabilität beim Bewegen prüfen.
4. **Dunst:** Luftperspektive statt Beigeschleier. Nah klar, Ferne bläulich aufgehellt, Bodendunst nur in Senken. Die 82-%-Obergrenze senken, bis H2 Tiefe zeigt, ohne den Vordergrund zu waschen.
5. **Nachbearbeitung:** Umgebungsverdeckung im Bildschirmraum, dezentes Bloom (Sonne, Kristalle, Lichtsäule), Lichtstrahlen bei Blick Richtung Sonne, zeitliche Kantenglättung mit Nachschärfen, Farbkorrektur über eine Farbtabelle, leichte Vignette. Jede Stufe einzeln abschaltbar und einer Qualitätsstufe zugeordnet.
6. **Tonemapping und Belichtung** messen statt raten: AgX, Neutral und ACES auf G1, G2, F1 gegen die Referenzbilder vergleichen (Kontrast, Sättigung, Himmelsfarbton), bestes wählen, Belichtung festlegen.

Fertig, wenn: Punkt „Licht und Atmosphäre" und „Himmel" auf allen Lesezeichen mindestens 7 (8 folgt mit den Objekten), Messlauf im Budget.

### Phase 2 — Boden, Fels am Hang, Wasser

1. **Gelände neu bauen ohne Änderung** (`tools/world/build_world.py`, Seed 73129) und die R16-Dateien mit den eingecheckten vergleichen. Sind sie nicht gleich, Abweichung dokumentieren und alle Platzierungstests (`tools/world/test_world.py`, `web/explore/test`) als Maßstab nehmen, bevor irgendetwas am Gelände geändert wird.
2. **Bodenschichten:** je Schicht Farbe, Normalen und eine Karte mit Verdeckung, Rauheit, Höhe; als Texturstapel in KTX2. Mischung über Höhenwerte (Gras wächst aus Erdfugen, Sand läuft in Kies aus) statt weicher Überblendung. Gegen Kachelmuster: zwei Maßstäbe, gedrehte Zweitprobe, großflächige Farbvariation.
3. **Makrokarte für die ganze Welt** (vom Weltgenerator erzeugt, etwa 4096² für 8 × 8 km): Schichtgewichte aus Hangneigung, Höhe, Abfluss, Feuchte; dazu großräumige Verdeckung (Himmelssicht aus der Höhenkarte) und später Kronenschatten aus den Baumplatzierungen. Diese Karte färbt auch das Gras, damit Halme und Boden zusammenpassen.
4. **Fels am Hang:** ab etwa 35° dreiseitig projizierte Kreide- und Schichtfels-Texturen mit waagrechten Bändern. Das ersetzt nicht die Klippenobjekte aus Phase 5, sorgt aber dafür, dass ihr Übergang zum Gelände stimmt.
5. **Wasser:** durchsichtig mit Tiefenfarbe (Türkis im Flachen, Blaugrün in der Tiefe, Grund sichtbar), zwei gegeneinander laufende Normalenkarten, Spiegelung aus der Umgebungskarte, auf hoher Stufe zusätzlich Bildschirmraum-Spiegelung, Schaum am Ufer und an Steinen, nasser dunkler Saum am Strand, Sonnenglitzern.
6. **Geländekorrekturen im Ausschnitt** nur wo ein Lesezeichen es verlangt: Strandbreite, eine Insel für das Inselmonument, ein Felsband am Rücken für F4. Danach alle Stand- und Auflagetests erneut.

Fertig, wenn: „Boden" und „Wasser" auf G1, G5, F1, F2, H1 mindestens 8.

### Phase 3 — Meshy-Pipeline bauen und kalibrieren (höchstens 150 Credits)

1. Werkzeuge aus Abschnitt 7 schreiben: `tools/meshy/` (Warteschlange, Budgetprüfung, Bildprüfung, Rohmodell-Blatt), `tools/blender/vrmeshy.py`, Erweiterung von `vr.py` (Quell-Hash) und `export_asset.py` (Klasse B ohne Neu-Bake, KTX2, vierte Detailstufe als Fernbild für Vegetation).
2. **Drei Pilot-Assets ganz durch die Kette bis ins Spiel:** `boulder_chalk_a` (B), `trunk_acacia_a` (B), `ruin_wall_a` (A).
3. Kalibrierungen, je einmal:
   - Bildmodell: derselbe Prompt mit `nano-banana-2-lite` und `gpt-image-2-5-flare`. Welches besteht die Checkliste öfter und liefert das bessere 3D?
   - Klasse: `boulder_chalk_a` einmal als B und einmal als A. Sieht man den Unterschied in G7 aus 3 m?
   - Tatsächliche Kosten je Aufruf gegen die Preisliste, inklusive Freistellen.
4. Ergebnis als feste Regeln in `docs/grafik/MESHY.md` schreiben (Standard-Bildmodell, Klassenwahl, bewährte Prompt-Bausteine, typische Fehler und ihre Behebung).

Fertig, wenn: die drei Pilot-Assets im Spiel aus der Nähe mindestens 8 erreichen. Wenn nicht, die Kette nachschärfen (Prompt, Klasse, Aufbereitung, Detailtextur), bevor weitere Credits fließen.

### Phase 4 — Vegetation

Das Bodenvideo besteht zu vier Fünfteln aus Vegetation. Hier entscheidet sich M1.

1. **Gras als Laufzeitsystem** statt GLB-Büschel: Halme je Geländezelle auf der Grafikkarte erzeugt, drei Ringe (nah echte Halme, mittel vereinfachte, fern breite Karten, die in die Bodentextur übergehen), Dichte und Höhe aus der Makrokarte, Farbe aus der Makrokarte plus Variation, Wind, dunkle Halmfüße statt Schattenwurf. Sichtweite auf hoher Stufe mindestens 90 m, lückenloser Übergang in die Fernfarbe.
2. **Bodenpflanzen:** Farne, großblättrige Stauden, Blumen, Trockengras-Horste als Karten aus Grok-Atlanten, in Gruppen gestreut, zellenweise als feste Instanzpakete.
3. **Bäume:** fünf Arten aus Meshy-Stämmen und Blender-Kronen (zwei Schirmakazien, Flaschenbaum, zwei Laubbäume), je zwei Kronenvarianten. Laub mit Durchlicht im Gegenlicht, weich gebogenen Normalen, Verdeckung im Kroneninneren, Wind in drei Ebenen (Stamm, Ast, Blatt). Ein gemeinsamer Laub-Atlas für alle Arten.
4. **Detailstufen:** 0 voll, 1 und 2 reduziert, 3 Fernbild. Umschalten mit Überblendung per Rasterung, damit nichts springt. Schatten nur von Stufe 0 und 1; ferne Bäume bekommen ihren Schatten aus der Makrokarte.
5. **Verteilung:** Wald, Hain, Wiese, Ufer als Karte; Bäume in Gruppen mit Lichtungen, Unterwuchs an Rändern, nichts auf Wegen, Sand und Fels. Zielgröße im Ausschnitt: einige tausend Bäume, Gras flächendeckend.
6. Kantenflimmern am Laub bekämpfen (Alpha-Test mit Abdeckungs-Kantenglättung oder zeitliche Glättung), mit den Bildfolgen prüfen.

Fertig, wenn: „Vegetation" auf G1–G4, F3, H1 mindestens 8, Bodenstrecke im Leistungsbudget.

### Phase 5 — Objektproduktion in Chargen

Reihenfolge: Felsbrocken und Klippen → Trümmer und Ruinen → Hero-Monumente → Kristall und Energie → Himmelskörper. Je Charge 5–8 Assets:

1. Briefe schreiben, Bilder erzeugen und prüfen (7.2).
2. 3D erzeugen und Rohmodelle prüfen (7.3, 7.4). Bild- und 3D-Aufrufe einer Charge nacheinander abschicken und gemeinsam abwarten.
3. Aufbereiten, Tor, Export (7.5).
4. Ins Spiel setzen, Schleife aus Abschnitt 6.

Parallel dazu die Blender-Bauten aus 9.2 (Rippenkrone, Viadukt, Kristallgrube, Lichtsäule) und die Überprüfung der 15 Alt-Assets.

Klippen werden an Steilhängen gesetzt (Platzierung aus der Hangneigung, von Hand an den Lesezeichen nachgeführt), am Fuß mit Geröll und Brocken verdeckt, oben mit Grasüberhang. Der Übergang zum Gelände nutzt dieselben Felstexturen wie Phase 2.

Fertig, wenn: alle Assets aus 9.1 exportiert oder mit Begründung gestrichen sind und „Fels und Bauten" auf G6, G7, F4 mindestens 8 erreicht.

### Phase 6 — Bildregie im Ausschnitt, dann M1

1. **Maßstab:** eine Rippenkrone von über 100 m am Seeufer, das Inselmonument im See, Tor mit Lichtsäule, Ruinenfeld am Hang, Kristallgrube auf der Anhöhe, zwei schwebende Körper und der Planet in den Sichtachsen von F1, F2, G3.
2. **Sichtachsen:** Von jedem Lesezeichen aus ist mindestens eine Landmarke im Dunst zu sehen. Wege führen auf Landmarken zu.
3. **Verdichten:** Trümmer an Bauten, Brocken an Hängen, Unterwuchs an Stämmen, Schilf und nasse Steine am Ufer.
4. **Schlussschleife** über alle 13 Lesezeichen und beide Bildfolgen bis zur Abnahme (6.2), höchstens 8 Runden.
5. **Leistungsrunde** (Abschnitt 11) auf allen Stufen, auch WebGL2.
6. **M1-Bericht:** Vergleichsbilder vorher, nachher und Vorlage für alle Lesezeichen, Noten, Messwerte, verbrauchte Credits, offene Mängel. Draft-PR. Danach ohne Warten weiter mit Phase 7; Marks Rückmeldung wird eingearbeitet, sobald sie kommt.

### Phase 7 — Ausrollen auf 8 × 8 km

1. **Platzierung kachelweise:** Regeln je 512-m-Kachel aus einer Biomkarte für die ganze Welt, Auflösung der Regeln in einem Web Worker, Laden und Entladen zusammen mit den Geländekacheln. Die eine große `placements.json` bleibt für handgesetzte Einzelobjekte.
2. **Fernsicht:** Bäume als Fernbilder bis mindestens 2,5 km, dahinter Waldfarbe und Kronenschatten in der Makrokarte; große Bauten und Klippen mit eigener grober Stufe bis zum Horizont.
3. **Regionen** nach `world/regions/regions.json`, je Region ein eigenes Gesicht aus dem vorhandenen Baukasten plus ein bis zwei Hero-Objekten: Schluchten mit Klippenbausatz und Felsnadeln, Viadukt und Sandsteinbogen im Canyon, Wasserfall an der Steilstufe, Rippenkronen und Tore als Fernziele. Geländeumbau, wo Schluchtwände zu flach sind.
4. **Lesezeichen je Region** aufnehmen und die Schleife fahren, Region für Region.
5. **Überflugstrecke** quer über die Welt als zweite Messstrecke; kein Ruckeln beim Nachladen (längstes Einzelbild unter 50 ms).
6. **M2-Bericht** wie bei M1.

### Phase 8 — Abschluss

Leistungs- und Speicherprüfung auf allen Stufen, Ladezeiten, WebGL2-Rückfall, `npm test`, `npm run build`, `vr.py check`, README und `web/explore/README.md` aktualisieren, `docs/grafik/` vervollständigen, Memory-Notiz, PR aus dem Entwurf holen. Schlussbericht mit ehrlicher Liste dessen, was hinter den Videos zurückbleibt.

## 11. Leistung

Messgerät ist dieser PC (RX 6600, 1080p). Gemessen wird auf den zwei festen Strecken, nicht an einer Stelle.

| Größe | Grenze auf Stufe „Hoch" |
|---|---|
| Bildrate | Mittel mindestens 60, schlechtestes Prozent mindestens 45 |
| Längstes Einzelbild beim Nachladen | unter 50 ms |
| Sichtbare Dreiecke | Richtwert 4 Mio. am Boden, 5 Mio. im Flug; maßgeblich ist die Bildzeit |
| Draw Calls | höchstens 400 |
| Texturspeicher auf der Grafikkarte | höchstens 1,5 GB |
| Download bis spielbar | höchstens 60 MB, Rest wird nachgeladen |
| Download des ganzen Ausschnitts | höchstens 250 MB |

Mittel dafür:

- **Vier Qualitätsstufen** (Niedrig, Mittel, Hoch, Ultra), wählbar über `?quality=` und automatisch aus den ersten Sekunden Bildzeit. Jede Stufe regelt Grasdichte und -sichtweite, Schattenkaskaden, Nachbearbeitung, Texturgröße, Sichtweiten.
- **Dynamische Auflösung** mit Hochskalierung, damit die Bildrate hält, bevor Details gestrichen werden.
- **KTX2** für alle Texturen (Normalen in hoher Qualität, Farbe stark komprimiert). Texturgrößen: Hero 2048², höchstens drei Objekte mit 4096², Requisiten 1024², ein gemeinsamer 2048²-Atlas für alles Laub.
- **Instanzen zellenweise** als feste Pakete für Kleinvegetation; Auswahl je Instanz nur für Bäume und große Objekte. Rechenarbeit für Streuung und Geländenetze in Web Worker.
- **Schatten sparsam:** nur nahe Detailstufen werfen Schatten, Gras gar nicht, Ferne über die Makrokarte.
- **Überzeichnung beim Laub** messen und über Kartenzahl und -größe begrenzen.
- Stufe „Mittel" muss auf integrierter Grafik mit 30 Bildern laufen; das wird mit gedrosselter Auflösung auf diesem PC angenähert und im Bericht als Schätzung gekennzeichnet.

`web/explore/perf-budget.json` hält die Grenzen; `bench.mjs` bricht mit Fehler ab, wenn eine gerissen wird.

## 12. Abnahme

M1 und M2 sind erreicht, wenn jeweils alles zutrifft:

1. Rubrik: Median mindestens 8 in jedem Punkt auf jedem Lesezeichen des Meilensteins, bewertet von drei unabhängigen Prüfern am letzten Stand.
2. Bildfolgen ohne Flimmern und ohne sichtbares Umschalten der Detailstufen.
3. Leistungsbudget auf „Hoch" eingehalten, „Mittel" und WebGL2 lauffähig.
4. Alle platzierten Objekte durch das Tor; `vr.py check`, Tests und Build grün.
5. Meshy-Verbrauch laut Kostenbuch höchstens 2000, jede Zeile mit Task-ID und Datei im Bibliotheksordner belegt.
6. Welt weiterhin 8 × 8 km, Ausschnitt weiterhin mindestens 1 × 1 km.
7. Bericht mit Vergleichsbildern, Messwerten und offener Mängelliste liegt vor.

Wird Punkt 1 nach den erlaubten Runden nicht erreicht, wird das **nicht** schöngeredet: Der Bericht nennt die Lesezeichen und Punkte unter 8, die Ursache und was es bräuchte.

## 13. Anhalten und fragen

Die Session läuft selbständig durch. Sie hält nur an bei:

- Meshy-Verbrauch erreicht 1800 Credits, oder ein Aufruf kostet deutlich mehr als die Preisliste.
- Meshy-Login abgelaufen oder Tarif reicht nicht (`plan_upgrade_required`).
- LFS-Größe über 800 MB vor einem Push.
- Die drei Pilot-Assets erreichen auch nach Nachschärfen keine 8 (Phase 3). Dann Vorschlag für eine andere Aufteilung zwischen Meshy und Blender vorlegen.
- Ein Schritt würde vorhandene Arbeit unwiederbringlich löschen.
- Zielqualität und Leistungsbudget lassen sich an einem Lesezeichen nicht zugleich erreichen. Dann beide Varianten mit Bild und Messwert vorlegen.

## 14. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Die Prüfer benoten zu freundlich | Prüfer sehen nur Bildpaare und Rubrik; feste Bedeutung der Noten; Farb- und Kontrastmessung als Gegenprobe; Mängelliste ist Pflicht, auch bei hoher Note |
| Meshy liefert Klumpen, flache Rückseiten oder eingebackenes Licht | Bild-Checkliste, laublose Stämme, Mehransicht für Hero-Objekte, automatische Rohmodell-Prüfung, höchstens eine Neu-Generierung |
| Credits reichen nicht | Kalibrierung zuerst, Posten-Grenzen, Kürzen der Liste von unten, Reserve nur nach Rückfrage |
| Große Meshy-Objekte wirken aus der Nähe unscharf | Detailtextur je Materialklasse, Lesezeichen G6 und G7 als Pflichtprüfung |
| Gras und Laub kosten zu viel Bildzeit | Drei Ringe, Stufen, dynamische Auflösung, Messlauf nach jedem Paket |
| Gelände lässt sich lokal nicht identisch neu erzeugen | Erst unveränderter Neubau und Vergleich; Platzierungstests als Maßstab |
| Lange Session verliert den Faden | `docs/grafik/STATE.md` nach jedem Paket, kleine Commits, Kostenbuch und Warteschlange außerhalb des Kontexts |
| Stil driftet Richtung Kopie der Vorlage | `art/STYLE.md` gilt: Licht, Rhythmus und Farbverhältnisse übernehmen, keine Fahrzeuge, Schriftzüge oder genauen Bauformen |
