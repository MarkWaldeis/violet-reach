import { chromium } from 'playwright';
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 640, height: 360 } });
await p.goto('http://localhost:5173/?cam=360,1.7,1680,-0.68,0&agl=1&freeze=1&quality=high&hud=0', { waitUntil: 'domcontentloaded' });
// wait for grass system to exist
for (let i = 0; i < 120; i++) {
  await new Promise(r => setTimeout(r, 1500));
  const has = await p.evaluate(() => !!(window).__grass).catch(() => false);
  if (has) break;
}
await new Promise(r => setTimeout(r, 20000)); // let cells build
const info = await p.evaluate(() => {
  const g = (window).__grass;
  if (!g) return { err: 'no __grass' };
  const s = g.sampler.sample(360, 1680);
  const s2 = g.sampler.sample(370, 1690);
  const h = g.terrain.fullHeightAt ? g.terrain.fullHeightAt(360, 1680) : 'n/a';
  const h2 = g.terrain.heightAt ? g.terrain.heightAt(360, 1680) : 'n/a';
  const cells = g.sys.group.children.length;
  const counts = g.sys.group.children.slice(0, 5).map(m => m.count);
  const stats = { ...g.sys.stats };
  // sample one instance matrix if exists
  let inst = null;
  if (cells) {
    const m = g.sys.group.children[0];
    const arr = m.instanceMatrix.array;
    inst = [arr[12], arr[13], arr[14]];
    const aInfo = m.geometry.getAttribute('aInfo');
    inst.push('aInfo0', aInfo ? [aInfo.getX(0), aInfo.getY(0), aInfo.getZ(0), aInfo.getW(0)] : 'missing');
  }
  const gdbg = (window).__gdbg;
  return { sample: s, sample2: s2, fullH: h, h: h2, cells, counts, stats, inst, gdbg };
});
console.log(JSON.stringify(info, null, 1).slice(0, 1400));
await b.close();
