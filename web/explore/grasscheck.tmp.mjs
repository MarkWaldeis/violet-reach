import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
const errors = [];
p.on('pageerror', e => errors.push('PAGEERROR: ' + String(e).slice(0, 200)));
await p.goto('http://localhost:5173/?cam=360,1.7,1680,-0.68,0&agl=1&freeze=1&quality=high&hud=0', { waitUntil: 'domcontentloaded' });
// wait until probe exists and frames are being rendered, regardless of full-ready
let framesOk = false;
for (let i = 0; i < 200 && !framesOk; i++) {
  await new Promise(r => setTimeout(r, 1500));
  framesOk = await p.evaluate(() => {
    if (!window.__vr) return false;
    const s = window.__vr.stats();
    return s.frame > 30 && s.triangles > 100000;
  }).catch(() => false);
  if (i % 20 === 19) {
    const st = await p.evaluate(() => window.__vr ? { f: window.__vr.stats().frame, t: window.__vr.stats().terrain.loaded + '/' + window.__vr.stats().terrain.total, ready: window.__vr.ready } : null).catch(() => null);
    console.log('progress', JSON.stringify(st));
  }
}
console.log(framesOk ? 'RENDERING' : 'NO-RENDER');
// give grass cells time to build (1/frame budget) and terrain to fill in
await new Promise(r => setTimeout(r, 15000));
await p.evaluate(() => window.__vr.frame()).catch(() => {});
await p.evaluate(() => window.__vr.frame()).catch(() => {});
const st = await p.evaluate(() => { const s = window.__vr.stats(); return { tris: s.triangles, draws: s.drawCalls, terrain: s.terrain.loaded + '/' + s.terrain.total, frames: s.frame }; }).catch(() => null);
console.log('STATS', JSON.stringify(st));
await p.screenshot({ path: 'C:/Users/Mark Waldeis/devin-screenshots/violet-reach/grass-g3-wide.png' });
await p.evaluate(() => window.__vr.setCamera(360, 0.9, 1680, -0.68, -0.35, { agl: true })).catch(() => {});
await new Promise(r => setTimeout(r, 12000));
await p.evaluate(() => window.__vr.frame()).catch(() => {});
await p.screenshot({ path: 'C:/Users/Mark Waldeis/devin-screenshots/violet-reach/grass-g3-close.png' });
console.log('ERRORS:', JSON.stringify(errors.slice(0, 4)));
await b.close();
