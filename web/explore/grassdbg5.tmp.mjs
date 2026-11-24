import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 640, height: 360 } });
const logs = [];
p.on('console', m => logs.push(m.type() + ': ' + m.text().slice(0, 140)));
p.on('pageerror', e => logs.push('PAGEERROR: ' + String(e).slice(0, 200)));
await p.goto('http://localhost:5173/?cam=360,1.7,1680,-0.68,0&agl=1&freeze=1&quality=high&hud=0&cb=' + Date.now(), { waitUntil: 'domcontentloaded' });
let frames0 = -1, frames1 = -1;
for (let i = 0; i < 100; i++) {
  await new Promise(r => setTimeout(r, 1500));
  const st = await p.evaluate(() => {
    const out = { vr: !!window.__vr, grass: !!(window).__grass, gdbg: (window).__gdbg ?? null, f: null, upd: null };
    if (window.__vr) out.f = window.__vr.stats().frame;
    if ((window).__grass) out.upd = (window).__grass.sys.stats.updates;
    return out;
  }).catch(() => null);
  if (st?.vr && frames0 < 0) frames0 = st.f;
  if (st?.f > 60) { frames1 = st.f; console.log('EVIDENCE', JSON.stringify(st)); break; }
  if (i === 99) console.log('ENDSTATE', JSON.stringify(st));
}
console.log('LOGS', JSON.stringify(logs.slice(0, 10), null, 1));
await b.close();
