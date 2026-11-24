import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
// eye-level shot straight into the meadow, slight downward pitch baked into URL
await p.goto('http://localhost:5173/?cam=360,1.7,1680,-0.68,-0.18&agl=1&freeze=1&quality=high&hud=0', { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 240; i++) {
  await new Promise(r => setTimeout(r, 1500));
  if (await p.evaluate(() => window.__vr?.stats().frame > 220).catch(() => false)) break;
}
await new Promise(r => setTimeout(r, 12000));
await p.evaluate(() => window.__vr.frame());
await p.screenshot({ path: 'C:/Users/Mark Waldeis/devin-screenshots/violet-reach/grass-final-a.png' });
const stats = await p.evaluate(() => ({ tris: window.__vr.stats().triangles, draws: window.__vr.stats().drawCalls, placed: window.__gdbg?.lastPlaced }));
console.log('FINAL', JSON.stringify(stats));
await b.close();
