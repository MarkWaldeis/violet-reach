# Violet Reach agent notes

## Verification

- Explorer tests: `cd web/explore && node --test test/*.test.ts`
- TypeScript/build: `cd web/explore && npm run build`
- Asset gate: `python tools/vr.py check`
- World checks: `python tools/world/test_world.py` and relevant `tools/world/test_*.py`

## QA captures

- Captures belong in `C:\Users\Mark Waldeis\devin-screenshots\violet-reach\`.
- Use `node tools/qa/capture.mjs` / `tools/qa/shot.mjs` on port `5198`; valid performance/visual captures require real Chrome, WebGPU and the AMD adapter.
- Do not manually start a reusable Vite QA server unless `VR_GATE_CACHE_MS` is set (normally `30000`). The world-content middleware otherwise runs the synchronous asset gate for every terrain/asset request, making captures appear hung. Prefer letting `capture.mjs` start its own correctly configured server.
- Do not run production builds or edit source files while captures are active; Vite watcher/HMR noise invalidates or destabilises runs.
