"""Generator regressions; run with Blender's bundled NumPy."""
import math
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_world import bank_rise, carve, hydrology, lake_radius


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
    print('PASS: overlapping river envelopes are order-independent, wet and below 30 degrees')
    print('PASS: flat wet margin, empty hydrology, deterministic paths and irregular lake coves')


if __name__ == '__main__':
    main()
