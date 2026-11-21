# Violet Reach — Multi-Session-Plan

Arbeitstitel **Violet Reach**: eine große, originale Fantasy-Welt im Stil der beiden Referenzvideos, komplett in Blender gebaut und im PC-Browser spielbar. Nicht verwendet wird die eigene 3D-Engine (`ai-native-3d-engine`).

## 1. Zielbild

Aus den Videos abgeleitet (Referenz für den Stil, nichts wird kopiert):

- Helle, stilisiert-realistische Fantasy-Landschaft: grüne Hügel, dichter Wald, Flüsse, Seen, Klippen, tiefe Canyons.
- Große weiße Monumentalbauten: Tore, Bögen, Brücken, Säulen, Ruinen, geschwungene Rippenbögen.
- Violette Kristalle, violette Energieobjekte, leuchtende Portale als Akzente.
- Schwebende Himmelskörper, Wolkenschichten, Dunst, weite Fernsicht.
- Zwei Perspektiven: schneller Überflug (im Video ca. 9,7 km in 50 s) und Gehen am Boden durch Gras und Bäume.

Umfang der Welt: 8 × 8 km begehbar, dahinter Fernkulisse. Sechs Regionen nach dem Vorbild der im Video sichtbaren Gebiete (Säulenschlucht, Canyon, Spießrutenlauf, Große Front, Sichel, Scheibensee), mit eigenen Namen und eigener Anordnung.

## 2. Ehrliche Einschätzung der Qualität

Die Videos sehen nach einer nativen High-End-Engine aus. Im Browser gibt es keine Entsprechung zu deren Geometrie- und Beleuchtungssystemen. Erreichbar ist: derselbe Stil, dieselbe Weite und sehr detaillierte Einzelobjekte, mit vorberechnetem Licht und Detailstufen statt Echtzeit-Global-Illumination. Ob das Ergebnis nah genug an den Videos liegt, zeigt Phase 2 (ein fertiger Ausschnitt) — dort wird entschieden, bevor die Massenproduktion startet.

## 3. Technik

| Bereich | Entscheidung | Grund |
|---|---|---|
| Modellierung | Blender, jedes Objekt als eigenes Skript `build.py` + eigene `.blend` | Reproduzierbar, von Sessions ohne Bildschirm baubar, jede Änderung im Git nachvollziehbar |
| Blender-Version | 5.3.0 (per Homebrew auf der Devin-Maschine installierbar; 5.2 bietet Homebrew nicht mehr an) | Auf Wunsch auf 5.2 festnagelbar |
| Prüf-Render | Cycles auf CPU | Auf der Devin-Maschine getestet: CPU-Cycles, EEVEE und glTF-Export laufen; Cycles auf der virtuellen GPU hängt |
| Austauschformat | glTF 2.0 (`.glb`), Meshopt-Kompression, KTX2-Texturen (im Fundament vorerst WebP) | Standard für den Browser, kleinste Downloads |
| Browser-Laufzeit | Three.js mit WebGPU-Renderer und WebGL2-Rückfall, TypeScript, Vite | Meistgenutzte Browser-3D-Bibliothek, keine eigene Engine |
| Gelände | In Blender erzeugte Höhenkarte, als 16-Bit-Kacheln exportiert, im Browser mit Detailstufen nachgeladen | 8 × 8 km sind als ein Mesh nicht ladbar |
| Vegetation | Instanzen mit 3–4 Detailstufen plus Bildtafel für die Ferne | Hunderttausende Bäume und Gras |
| Licht | Sonne mit kaskadierten Schatten, vorberechnete Umgebungsverdeckung pro Objekt, Atmosphäre und Dunst als Shader | Bezahlbar im Browser |
| Auslieferung | GitHub Pages | Läuft direkt aus dem Repo |

Leistungsziel: 60 Bilder/s bei 1080p auf einer Mittelklasse-Grafikkarte, höchstens 2 Mio. sichtbare Dreiecke, höchstens 1500 Zeichenaufrufe, erster Download unter 60 MB, der Rest wird beim Fliegen nachgeladen.

## 4. Das Qualitätstor: erst Blender, dann Spiel

Jedes Objekt durchläuft dieselben Stufen. Der Status steht in `assets/<kategorie>/<id>/asset.json`.

| Status | Bedeutung | Wer |
|---|---|---|
| `planned` | Im Register mit Beschreibung, Maßen, Referenzbild | Lead |
| `modeling` | `build.py` erzeugt die hochdetaillierte Quelle in Blender | Bau-Session |
| `blender_review` | Prüfblatt gerendert: 8 Ansichten rundum, 2 Nahaufnahmen, Drahtgitter, Maßfigur | Bau-Session |
| `approved` | Prüfer hat das Blatt gegen die Checkliste bewertet und freigegeben | Prüf-Session (nie die Bau-Session selbst) |
| `exported` | Detailstufen, gebackene Texturen, `.glb` erzeugt | Automatisch |
| `in_game` | In einer Region platziert | Regions-Session |

Regeln:

1. Das Export-Werkzeug weigert sich bei jedem Objekt, das nicht `approved` ist. Eine automatische Prüfung im Repo (CI) lässt keinen Pull Request durch, der ein nicht freigegebenes Objekt ins Spiel bringt.
2. Checkliste des Prüfers, je 1–10, Freigabe ab 8 in jedem Punkt: Silhouette, Detailgrad der Form, Material und Oberfläche, Maßstab, Stiltreue zum Stilhandbuch, keine Fehler (Löcher, Durchdringungen, gestreckte Texturen).
3. Abgelehnte Objekte gehen mit konkreten Mängeln zurück an eine Bau-Session, höchstens drei Runden, danach entscheidet der Lead über Neuansatz.
4. Pro Charge bekommt Waldeis ein Sammelblatt der freigegebenen Objekte und kann einzelne zurückweisen.
5. Höchste Detailstufe gilt für die Blender-Quelle. Ins Spiel gehen daraus abgeleitete Detailstufen, deren nächste Stufe gegen die Quelle gebacken ist (Normalen, Verdeckung), damit das Detail sichtbar bleibt.

## 5. Repo-Aufbau

```
assets/<kategorie>/<id>/   build.py, asset.json, review/ (Prüfblätter), export/ (.glb)
art/                       Stilhandbuch, Farbpalette, Referenzbilder, Materialbibliothek
world/                     Höhenkarte, Regionskarten, Platzierungsdaten
tools/                     Bauen, Prüfblatt rendern, Tor prüfen, Exportieren; `vr.py status` listet alle Objekte
web/                       Three.js-Laufzeit
docs/                      PLAN.md, Anleitungen für Sessions
```

Jede Session arbeitet in einem eigenen Zweig und fasst nur ihren Objektordner an, dadurch keine Konflikte zwischen parallelen Sessions. Die `.blend` wird nicht eingecheckt, sie ist jederzeit aus `build.py` neu erzeugbar. Exportierte `.glb` liegen in Git LFS.

## 6. Phasen und Sessions

Der Plan stammt aus einer Fable-5.2-Session. Alle Bau-, Prüf- und Regions-Sessions laufen als eigene Fusion-Sessions. Ein Lead (der Bot) führt ein Ticket pro Session; der Stand jedes Objekts steht in seiner `asset.json`. Eine Session entspricht etwa einer Woche menschlicher Arbeit.

| Phase | Inhalt | Sessions | Abhängig von |
|---|---|---|---|
| 0 Fundament | Werkzeuge für Tor, Prüfblatt und Export, ein Beweisobjekt von Blender bis Browser | 1 | Repo mit diesem Plan |
| 1 Grundlagen | A Stilhandbuch und Materialbibliothek · B Laufzeit-Kern (Gelände-Nachladen, Himmel, Flug- und Gehkamera) · C Weltentwurf (Höhenkarte 8 × 8 km, Regionen, Flüsse) | 3 parallel | 0 |
| 2 Ausschnitt | Ein Gebiet von 1 × 1 km komplett fertig mit rund 25 Objekten, Licht, Wasser, beide Kameras. Waldeis entscheidet: weiter, nachbessern oder Stil ändern | 4 Bau + 1 Prüf + 1 Zusammenbau | 1 |
| 3 Objektproduktion | Chargen von 5–8 Objekten je Session, siehe Liste unten | 22 Bau + 6 Prüf, je 6–8 gleichzeitig | 2 freigegeben |
| 4 Regionen | Je Region eine Session: Platzierung, Übergänge, Wege, Landmarken | 6 | 3 je Region |
| 5 Stimmung | Licht, Atmosphäre, Wolken, Wasser, Kristall-Leuchten, Portal-Effekte | 2 | 4 |
| 6 Feinschliff | Leistung messen und senken, Ladezeiten, Fehlerjagd mit aufgezeichneten Durchflügen, Veröffentlichung | 2–3 | 5 |

Zusammen rund 45–50 Sessions und rund 170 Einzelobjekte.

Chargen in Phase 3:

| Familie | Objekte | Sessions |
|---|---|---|
| Bäume (6 Arten × 3 Varianten) | 18 | 3 |
| Sträucher, Bodenpflanzen, Gras, Blumen | 20 | 3 |
| Felsen, Geröll, Klippenstücke | 16 | 2 |
| Canyon-Wände und Felssäulen | 14 | 2 |
| Weiße Monumente: Tore, Bögen, Säulen, Rippenbögen | 20 | 3 |
| Brücken und Viadukte | 8 | 1 |
| Ruinen und Trümmer | 16 | 2 |
| Violette Kristalle und Energieobjekte | 14 | 2 |
| Portale und Landmarken | 8 | 2 |
| Schwebende Inseln und Himmelskörper | 8 | 1 |
| Wasserfälle, Uferstücke, Seeobjekte | 10 | 1 |

## 7. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Per Skript gebaute Objekte wirken zu einfach | Phase 2 als Prüfstein; Materialbibliothek mit gebackenen Oberflächendetails; Prüfer vergleicht mit den Videobildern |
| Browser schafft die Weite nicht flüssig | Leistungsziel wird ab Phase 1 bei jedem Pull Request gemessen |
| Stil driftet zwischen 30 Bau-Sessions | Ein Stilhandbuch, eine Materialbibliothek, ein Prüfer-Maßstab |
| Speicherplatz für große Dateien bei GitHub | `.blend` neu erzeugbar halten, nur Exporte und Prüfblätter speichern |

## 8. Offene Punkte für Waldeis

1. Reine Blender-Modellierung ist der Standard. Erlaubt wäre auch: KI-generierte Rohformen (wie in den älteren Projekten) als Ausgangspunkt, die dann in Blender ausgearbeitet werden. Ohne Antwort bleibt es bei reinem Blender.
2. Nur Erkunden (Fliegen und Gehen) oder auch Spielmechanik? Ohne Antwort: nur Erkunden.
