import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 960, height: 540 } });
const errs = [];
p.on('console', m => { if (m.type() !== 'debug') errs.push(m.type() + ': ' + m.text().slice(0, 220)); });
await p.goto('http://localhost:5173/?cam=360,1.7,1680,-0.68,0&agl=1&freeze=1&quality=high&hud=0', { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 240; i++) {
  await new Promise(r => setTimeout(r, 1500));
  const warm = await p.evaluate(() => window.__vr?.stats().frame > 200).catch(() => false);
  if (warm) break;
}
await new Promise(r => setTimeout(r, 20000));
const diag = await p.evaluate(async () => {
  const g = window.__grass.sys;
  const out = { meshes: g.group.children.length, visible: [], positions: [], sphere: null, parentVisible: g.group.visible, inScene: !!g.group.parent };
  const m = g.group.children[0];
  if (m) {
    out.visible.push(m.visible);
    const arr = m.instanceMatrix.array;
    out.positions.push([arr[12], arr[13], arr[14]]);
    const bs = m.geometry.boundingSphere;
    out.sphere = bs ? { c: [bs.center.x, bs.center.y, bs.center.z], r: bs.radius } : 'null';
    out.count = m.count;
    out.frustumCulled = m.frustumCulled;
    out.matType = m.material?.type;
    out.hasPosNode = !!m.material?.positionNode;
    // camera pos for reference
    out.cam = window.__vr.stats().camera;
  }
  return out;
});
console.log('DIAG', JSON.stringify(diag, null, 1));
// test 1: disable culling everywhere + force visible, screenshot
await p.evaluate(() => {
  for (const m of window.__grass.sys.group.children) m.frustumCulled = false;
});
await p.evaluate(() => window.__vr.frame());
await p.evaluate(() => window.__vr.frame());
const after1 = await p.evaluate(() => ({ tris: window.__vr.stats().triangles, draws: window.__vr.stats().drawCalls }));
console.log('AFTER-NOCULL', JSON.stringify(after1));
console.log('ERRS', JSON.stringify(errs.slice(0, 6)));
await b.close();
