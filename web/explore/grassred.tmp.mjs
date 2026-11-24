import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 960, height: 540 } });
await p.goto('http://localhost:5173/?cam=360,1.7,1680,-0.68,0&agl=1&freeze=1&quality=high&hud=0', { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 240; i++) {
  await new Promise(r => setTimeout(r, 1500));
  if (await p.evaluate(() => window.__vr?.stats().frame > 200).catch(() => false)) break;
}
await new Promise(r => setTimeout(r, 15000));
await p.evaluate(() => window.__grass.sys.debugBasicMaterial());
  await p.evaluate(() => window.__vr.frame());
await p.evaluate(() => window.__vr.frame());
await new Promise(r => setTimeout(r, 1500));
await p.screenshot({ path: 'C:/Users/Mark Waldeis/devin-screenshots/violet-reach/grass-red-test.png' });
console.log('done');
await b.close();
