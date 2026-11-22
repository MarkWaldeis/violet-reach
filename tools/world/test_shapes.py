"""Generator regressions; run with Blender's bundled NumPy."""
import math
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_world import bank_rise, carve, hydrology, lake_radius, lake_distance, lake_outline


def main():
    axis = np.arange(-160, 162, 2, dtype=np.float32)
    high = np.full((len(axis), len(axis)), 80, dtype=np.float32)
    rivers = [('First', np.array([[-160, 0, 10, 20], [160, 0, 10, 20]])),
              ('Second', np.array([[-160, 70, 15, 24], [160, 70, 15, 24]]))]
    a = carve(high.copy(), axis, rivers, [])
    b = carve(high.copy(), axis, list(reversed(rivers)), [])
    np.testing.assert_array_equal(a, b)
    assert np.max(np.abs(np.diff(a, axis=0)))/2 < math.tan(math.radians(30))
    assert np.all(a[len(axis)//2] < 10)
    np.testing.assert_array_equal(carve(high.copy(), axis, [], []), high)
    assert np.max(np.diff(bank_rise(np.arange(0, 100, .1))))/.1 < math.tan(math.radians(30))
    assert bank_rise(4) < .4
    paths, lakes = hydrology()
    again, _ = hydrology()
    for (_, p), (_, q) in zip(paths, again):
        np.testing.assert_array_equal(p, q)
        assert np.all(np.diff(p[:, 2]) <= 0)
    for _, cx, cy, radius, _ in lakes:
        r = lake_radius(np.linspace(0, 2*np.pi, 384, endpoint=False), radius)
        assert np.ptp(r) > radius*.3
    lake = ('Test', 0, 0, 100, 10)
    mouth = [('Inflow', np.array([[-200, 0, 10, 30], [0, 0, 10, 30]]))]
    outline = lake_outline(lake, mouth)
    assert np.max(np.linalg.norm(np.diff(np.vstack((outline,outline[:1])),axis=0),axis=1)) < 20
    np.testing.assert_allclose(lake_distance(outline[:,0],outline[:,1],lake,mouth),18,atol=.001)
    assert np.min(outline[:,0]) < -200
    plain = lake_outline(lake, [])
    np.testing.assert_allclose(lake_distance(plain[:,0],plain[:,1],lake,[]),18,atol=.001)
    for lake in lakes:
        _,cx,cy,r,level = lake
        outline = lake_outline(lake,paths)
        for x,y in outline:
            nearest,water = math.inf,math.inf
            for _,points in paths:
                for a,b in zip(points[:-1],points[1:]):
                    delta = b[:2]-a[:2]
                    t = np.clip(np.dot([x-a[0],y-a[1]],delta)/np.dot(delta,delta),0,1)
                    d = np.hypot(x-a[0]-t*delta[0],y-a[1]-t*delta[1])-(a[3]+t*(b[3]-a[3]))*.5
                    if d<nearest:
                        nearest,water = d,a[2]+t*(b[2]-a[2])
            if nearest<5:
                assert abs(water-level)<.001, 'Mouth water must meet the expanded lake at lake level'
    print('PASS: overlapping river envelopes are order-independent, wet and below 30 degrees')
    print('PASS: flat wet margin, empty hydrology, deterministic paths and irregular lake coves')
    print('PASS: smooth river/lake mouth union has a continuous curved dry shoreline')


if __name__ == '__main__':
    main()
