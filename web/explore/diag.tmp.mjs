import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage();
const bad = [];
p.on('response', r => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.url().slice(-80)); });
await p.goto('http://localhost:5173/?cam=460,2.2,1560,0.5,-0.12&agl=1&freeze=1&quality=medium', { waitUntil: 'domcontentloaded' });
for (const wait of [15, 30, 45, 60, 90, 120]) {
  await new Promise(r => setTimeout(r, 15000));
  const st = await p.evaluate(() => ({
    status: document.querySelector('#status')?.textContent ?? '?',
    vr: !!window.__vr, ready: window.__vr?.ready,
  })).catch(e => ({ err: String(e).slice(0, 100) }));
  console.log(`t~${wait}s`, JSON.stringify(st));
}
console.log('HTTP>=400:', JSON.stringify(bad.slice(0, 8)));
await b.close();
