# Violet Reach · Erkundung

Die Three.js-Laufzeit liegt separat vom Blender-Objektviewer. Sie lädt Höhenkacheln nach Bedarf und rendert sie in vier Detailstufen. Standardmäßig zeigt sie eine generierte **Testlandschaft**, keine freigegebenen Kartenobjekte. Sie verwendet keine eigene 3D-Engine.

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

## Blender-Höhenkarte anbinden

Den exportierten Ordner `world/terrain/runtime/` unverändert statisch bereitstellen, zum Beispiel unter `web/explore/public/terrain/`. Dann die Vorschau mit `?terrain=./terrain/manifest.json` öffnen. Bei separatem Hosting muss der Server CORS erlauben. Nach dem Build ist `dist/` ohne Serverlogik statisch auslieferbar.

Manifest v1 enthält `version: 1`, `tilesX`, `tilesZ`, `tileSize` in Metern, `samples` pro Kante (17, 33, 65, 129 oder 257), `originX`, `originZ`, `minHeight` und `maxHeight` in Metern. Optional setzt `spawn: {x,z,yaw}` den Startpunkt; `yaw` ist in Radiant, bei Null blickt die Kamera nach Norden (−Z). Wenn kein Startpunkt angegeben ist, beginnt der Flug in der Mitte der Karte.

Neben dem Manifest liegt für jede Null-basierte Kachel eine Datei `<x>_<z>.r16` mit `samples²` vorzeichenlosen 16-Bit-Werten in Little-Endian. Zeilen laufen nach +Z (Süden), Spalten nach +X (Osten); +Y ist oben. Beide Nachbarn enthalten dieselben Randwerte. `minHeight + sample / 65535 * (maxHeight - minHeight)` ergibt die Höhe. Der Export ist von der Laufzeit unabhängig; Regions- und Hydrologiedaten werden hier noch nicht gerendert.

**Streaming:** Vier parallele Requests; zuerst die nächsten Kacheln. Aktive Kacheln sind durch Radius und Anzahl begrenzt. Höhen werden einmal pro Aufenthalt geladen und bei Bedarf für den Render-LOD ausgedünnt; Geometrie außerhalb der Reichweite wird freigegeben. Der Gehboden folgt den gerenderten Dreiecken, und die Kamera wartet an der Kante, wenn eine benötigte Kachel noch fehlt.
