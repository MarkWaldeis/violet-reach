import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
await p.goto('http://localhost:5173/?cam=360,1.7,1680,-0.68,0&agl=1&freeze=1&quality=high&hud=0', { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 240; i++) {
  await new Promise(r => setTimeout(r, 1500));
  const st = await p.evaluate(() => {
    if (!window.__vr || !(window).__grass) return null;
    const g = (window).__grass.sys.stats;
    return { f: window.__vr.stats().frame, upd: g.updates, placed: g.placed, skipH: g.skipHeight, skipD: g.skipDensity, cells: g.cells, meshes: (window).__grass.sys.group.children.length };
  }).catch(() => null);
  if (st && st.f > 200 && st.upd > 200) { console.log('WARM', JSON.stringify(st)); break; }
  if (i % 40 === 39) console.log('progress', JSON.stringify(st));
}
await new Promise(r => setTimeout(r, 20000)); // cells build 1/frame -> wait for ring fill
const st2 = await p.evaluate(() => {
  const g = (window).__grass.sys.stats;
  return { placed: g.placed, skipH: g.skipHeight, skipD: g.skipDensity, meshes: (window).__grass.sys.group.children.length, tris: window.__vr.stats().triangles, draws: window.__vr.stats().drawCalls };
});
console.log('FINAL', JSON.stringify(st2));
await p.screenshot({ path: 'C:/Users/Mark Waldeis/devin-screenshots/violet-reach/grass-v-wide.png' });
await p.evaluate(() => window.__vr.setCamera(362, 1.0, 1682, -0.68, -0.42, { agl: true }));
await new Promise(r => setTimeout(r, 10000));
await p.evaluate(() => window.__vr.frame());
await p.screenshot({ path: 'C:/Users/Mark Waldeis/devin-screenshots/violet-reach/grass-v-close.png' });
await b.close();
