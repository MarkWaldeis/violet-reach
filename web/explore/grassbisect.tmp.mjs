import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 960, height: 540 } });
await p.goto('http://localhost:5173/?cam=360,1.7,1680,-0.68,0&agl=1&freeze=1&quality=high&hud=0', { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 240; i++) {
  await new Promise(r => setTimeout(r, 1500));
  if (await p.evaluate(() => window.__vr?.stats().frame > 200).catch(() => false)) break;
}
await new Promise(r => setTimeout(r, 12000));
// A: clone material WITHOUT positionNode (color pipeline intact)
await p.evaluate(() => {
  const sys = window.__grass.sys;
  const orig = sys.group.children[0].material;
  window.__origMat = orig;
  const noPos = orig.clone();
  noPos.positionNode = null;
  for (const m of sys.group.children) m.material = noPos;
});
await p.evaluate(() => window.__vr.frame());
await p.evaluate(() => window.__vr.frame());
await new Promise(r => setTimeout(r, 1000));
await p.screenshot({ path: 'C:/Users/Mark Waldeis/devin-screenshots/violet-reach/grass-test-nopos.png' });
// B: clone WITH positionNode but plain green colorNode removed complexities: strip color/emissive nodes
await p.evaluate(async () => {
  const sys = window.__grass.sys;
  const orig = window.__origMat;
  const plainCol = orig.clone();
  plainCol.colorNode = null;
  plainCol.emissiveNode = null;
  plainCol.color?.set?.(0.2, 0.6, 0.15);
  for (const m of sys.group.children) m.material = plainCol;
});
await p.evaluate(() => window.__vr.frame());
await p.evaluate(() => window.__vr.frame());
await new Promise(r => setTimeout(r, 1000));
await p.screenshot({ path: 'C:/Users/Mark Waldeis/devin-screenshots/violet-reach/grass-test-plaincol.png' });
console.log('done');
await b.close();
