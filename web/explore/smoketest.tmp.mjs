import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome', args: ['--use-angle=vulkan', '--enable-unsafe-webgpu'] });
const p = await b.newPage({ viewport: { width: 960, height: 540 } });
const errors = [];
p.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)); });
p.on('pageerror', e => errors.push('PAGEERROR: ' + String(e).slice(0, 200)));
await p.goto(process.argv[2], { waitUntil: 'domcontentloaded' });
let ready = false;
for (let i = 0; i < 120 && !ready; i++) {
  await new Promise(r => setTimeout(r, 2000));
  ready = await p.evaluate(() => window.__vr?.ready ?? false).catch(() => false);
}
console.log(ready ? 'READY' : 'TIMEOUT');
if (ready) {
  await p.evaluate(() => window.__vr.frame());
  await p.evaluate(() => window.__vr.frame());
  const st = await p.evaluate(() => window.__vr.stats());
  console.log('STATS', JSON.stringify({ tris: st.triangles, draws: st.drawCalls, fps: st.fps, backend: st.backend }));
}
await p.screenshot({ path: process.argv[3] });
console.log('ERRORS:', JSON.stringify(errors.slice(0, 5)));
await b.close();
