# Konzeptquelle `ruin_blocks_a`

## Vorgeschriebener Grok-Versuch

Der erste Schritt war ein frischer Grok-CLI-Prozess in diesem Asset-Ordner:

```sh
grok -p "Generate one square concept/reference image for a game asset: a modular cluster of ancient ivory-white limestone ruin blocks and broken masonry fragments, arranged as one coherent grounded group about 7 metres wide, individual blocks ranging 0.8 to 4 metres. Matte weathered chalk and pale sandstone look, colors near #E8DABE and #DCCDB1 with cool grey shadow in cracks, chipped broken arrises, cracked faces, a few visible stone joints, light soil and sparse dark olive moss accumulation only near the base. Stable on the ground, nothing floating, no paper-thin slabs, no ornaments, no text, no people. Three-quarter slightly elevated view, whole group visible and centered, neutral pale grey studio background, soft even daylight, stylized-realistic fantasy world asset reference, crisp silhouette, fine stone pores." --always-approve
```

Ergebnis: **kein Bild**. Der interne `image_gen`-Aufruf meldete zunächst HTTP 429 (`resource-exhausted`, Rate-Limit bei `grok-imagine-image-2.0-low`). Nach der Warte-/Retry-Logik brach die Grok-CLI selbst mit HTTP 402 ab:

```text
personal-team-blocked:spending-limit: You have run out of credits or need a Grok subscription.
```

Ein minimaler Text-only-Kontrollaufruf (`Antworte nur: OK`) scheiterte anschließend ebenfalls mit HTTP 402. Damit war Grok in dieser Session technisch nicht verfügbar; es wurde **kein Meshy-Credit** und nachweislich auch kein erfolgreicher Grok-Bildaufruf verbraucht.

## Fallback im Asset-Ordner

`reference_concept_fallback.png` ist ein lokal erzeugtes, creditfreies Layout- und Stil-Moodboard. Es kombiniert:

- ein isometrisches Layoutschema der geplanten Blockgruppe (Gruppenbreite ca. 7,2 m, Einzelteile 0,8–4,0 m),
- die Projekt-Palette (`monument_white`, `stone_weathered`, `monument_shadow`, `moss`, `soil`),
- vorhandene Projekt-Referenzbilder `art/reference/ref_06_weathered_wall.jpg`, `ref_03_canyon_cliffs.jpg`, `ref_04_white_ribbed_arches.jpg`.

QA-Sichtung: Das Bild ist als **schematische Layout- und Palettenreferenz** brauchbar. Es ist ausdrücklich kein Grok-Ergebnis und keine fotorealistische Zielvorgabe; die isometrische Zeichnung ist vereinfacht. Die endgültige Form muss an `ruin_wall_a`, `column_white_a`, `monument_split_disc_a` und `art/STYLE.md` gemessen werden.
