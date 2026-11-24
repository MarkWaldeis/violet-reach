import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 960, height: 540 } });
await p.goto('http://localhost:5173/?cam=360,1.7,1680,-0.68,0&agl=1&freeze=1&quality=high&hud=0', { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 240; i++) {
  await new Promise(r => setTimeout(r, 1500));
  if (await p.evaluate(() => window.__vr?.stats().frame > 200).catch(() => false)) break;
}
await new Promise(r => setTimeout(r, 12000));
const r = await p.evaluate(async () => {
  const tsl = await import('/node_modules/.vite/deps/three_tsl.js?v=x').catch(() => null);
  return { tslLoaded: !!tsl };
});
console.log('tsl direct:', JSON.stringify(r));
// simplest decisive test: set positionNode = positionLocal passthrough on a clone
const res = await p.evaluate(async () => {
  try {
    const sys = window.__grass.sys;
    const orig = sys.group.children[0].material;
    // grab TSL from the already-loaded module graph via the material's constructor trick:
    // use the positionLocal exported through any existing node chain — instead, simplest: test with a FIXED offset vector
    // Test X: keep material but replace positionNode with constant unshifted passthrough using the ORIGINAL pipeline
    const clone = orig.clone();
    clone.positionNode = null; // baseline: visible grass expected
    for (const m of sys.group.children) m.material = clone;
    return { ok: true };
  } catch (e) { return { err: String(e).slice(0, 200) }; }
});
console.log('setup', JSON.stringify(res));
await p.evaluate(() => window.__vr.frame());
await p.evaluate(() => window.__vr.frame());
await new Promise(r2 => setTimeout(r2, 800));
const stats = await p.evaluate(() => ({ tris: window.__vr.stats().triangles, draws: window.__vr.stats().drawCalls }));
console.log('nullpos-stats', JSON.stringify(stats));
await p.screenshot({ path: 'C:/Users/Mark Waldeis/devin-screenshots/violet-reach/grass-nullpos.png' });
await b.close();
