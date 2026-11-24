import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 960, height: 540 } });
await p.goto('http://localhost:5173/?cam=460,2.2,1560,0.5,-0.12&agl=1&freeze=1&quality=medium', { waitUntil: 'domcontentloaded' });
let ready = false;
for (let i = 0; i < 150 && !ready; i++) {
  await new Promise(r => setTimeout(r, 2000));
  ready = await p.evaluate(() => window.__vr?.ready ?? false).catch(() => false);
}
console.log(ready ? 'READY' : 'TIMEOUT-after-300s');
if (ready) {
  await p.evaluate(() => window.__vr.frame());
  const st = await p.evaluate(() => window.__vr.stats());
  console.log('STATS', JSON.stringify({ tris: st.triangles, draws: st.drawCalls }));
}
await p.screenshot({ path: 'C:/Users/Mark Waldeis/devin-screenshots/violet-reach/grass-smoke-1.png' });
await b.close();
