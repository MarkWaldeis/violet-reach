"""Validate the runtime handoff with Python's standard library only."""
from array import array
from functools import lru_cache
import json
import math
from pathlib import Path
import struct
import sys
import zlib

WORLD = Path(__file__).resolve().parents[2] / 'world'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    runtime = WORLD / 'terrain/runtime'
    manifest = json.loads((runtime/'manifest.json').read_text())
    expected = dict(version=1, tilesX=16, tilesZ=16, tileSize=512, samples=257,
                    originX=-4096, originZ=-4096)
    for key, value in expected.items():
        require(manifest[key] == value, f'Incorrect manifest {key}')
    low, high = manifest['minHeight'], manifest['maxHeight']
    require(math.isfinite(low) and math.isfinite(high) and high > low, 'Invalid height range')
    files = list(runtime.glob('*.r16'))
    require(len(files) == 256, f'Expected 256 tiles, found {len(files)}')

    @lru_cache(maxsize=256)
    def tile(x, z):
        raw = (runtime/f'{x}_{z}.r16').read_bytes()
        require(len(raw) == 257*257*2, f'Incorrect byte count: {x}_{z}')
        values = array('H', raw)
        if sys.byteorder != 'little':
            values.byteswap()
        return values

    minimum, maximum = 65535, 0
    for z in range(16):
        for x in range(16):
            values = tile(x, z)
            minimum, maximum = min(minimum, min(values)), max(maximum, max(values))
            if x < 15:
                require(values[256::257] == tile(x+1, z)[0::257], f'East seam {x}_{z}')
            if z < 15:
                require(values[-257:] == tile(x, z+1)[:257], f'South seam {x}_{z}')
            for v in values[::509]:
                height = low + v/65535*(high-low)
                require(round((height-low)/(high-low)*65535) == v, 'Height decode round trip failed')
    require((minimum, maximum) == (0, 65535), 'Height range not fully used')
    metadata = json.loads((WORLD/'terrain/terrain.json').read_text())
    require(metadata['h_min'] == low and metadata['h_max'] == high, 'Metadata range mismatch')
    require(metadata['spacing'] == 2 and metadata['samples'] == 4097, 'Incorrect grid')
    require(metadata['tileSize'] == 512 and metadata['tileSamples'] == 257, 'Incorrect metadata tiles')
    require(metadata['extent'] == [-4096, -4096, 4096, 4096], 'Incorrect extent')
    print('PASS: 256 little-endian R16 tiles, 257×257; all 480 seams bit-identical')
    print('PASS: manifest, metadata, full 4097² grid and height decode round trip')

    data = (WORLD/'regions/regions.png').read_bytes()
    require(data[:8] == b'\x89PNG\r\n\x1a\n', 'Region PNG signature')
    offset, compressed = 8, bytearray()
    while offset < len(data):
        size = struct.unpack_from('>I', data, offset)[0]
        kind, body = data[offset+4:offset+8], data[offset+8:offset+8+size]
        crc = struct.unpack_from('>I', data, offset+8+size)[0]
        require(zlib.crc32(kind+body) & 0xffffffff == crc, 'Region PNG CRC')
        if kind == b'IHDR':
            width, height, depth, color, *_ = struct.unpack('>IIBBBBB', body)
        elif kind == b'IDAT':
            compressed.extend(body)
        offset += size+12
    require((width, height, depth, color) == (1025, 1025, 8, 0), 'Region PNG dimensions/format')
    raw = zlib.decompress(compressed)
    require(len(raw) == height*(width+1), 'Region map data size')
    indices = set()
    for row in range(height):
        start = row*(width+1)
        require(raw[start] == 0, 'Unsupported PNG row filter')
        indices.update(raw[start+1:start+width+1])
    regions = json.loads((WORLD/'regions/regions.json').read_text())['regions']
    require(indices == {r['index'] for r in regions} == set(range(1, 7)), 'Missing region index')
    require(len({r['id'] for r in regions}) == 6, 'Duplicate region id')
    print('PASS: six regions present; 1025² index PNG has no uncovered pixels')

    def sample(x, z):
        gx, gz = (x+4096)/2, (z+4096)/2
        ix, iz = max(0, min(4096, round(gx))), max(0, min(4096, round(gz)))
        tx, tz = min(15, ix//256), min(15, iz//256)
        v = tile(tx, tz)[(iz-tz*256)*257+ix-tx*256]
        return low + v/65535*(high-low)

    water = json.loads((WORLD/'hydrology.json').read_text())
    require(len(water['rivers']) >= 4 and 2 <= len(water['lakes']) <= 3, 'Hydrology missing')
    for river in water['rivers']:
        points = river['polyline']
        require(len(points) >= 2, f'Empty river {river["name"]}')
        require(all(len(p) == 4 and all(math.isfinite(v) for v in p) and p[3] > 0 for p in points), 'Invalid river point')
        require(all(-4096 <= p[0] <= 4096 and -4096 <= p[1] <= 4096 for p in points), 'River outside world extent')
        require(all(b[2] <= a[2] for a, b in zip(points, points[1:])), f'River ascends: {river["name"]}')
        require(all(sample(p[0],p[1]) < p[2] for p in points), f'Dry river centreline: {river["name"]}')
    for lake in water['lakes']:
        outline, level = lake['outline'], lake['water_y']
        require(len(outline) >= 16 and math.isfinite(level), 'Invalid lake')
        def river_mouth(x,z):
            x,z = round((x+4096)/2)*2-4096,round((z+4096)/2)*2-4096
            for river in water['rivers']:
                for a,b in zip(river['polyline'],river['polyline'][1:]):
                    dx,dz = b[0]-a[0],b[1]-a[1]
                    t = max(0,min(1,((x-a[0])*dx+(z-a[1])*dz)/(dx*dx+dz*dz or 1)))
                    width = a[3]+t*(b[3]-a[3])
                    distance = math.hypot(x-a[0]-t*dx,z-a[1]-t*dz)
                    bank = max(0,distance-width*.5)
                    river_level = a[2]+t*(b[2]-a[2])
                    ceiling = river_level-.35+.035*bank+.35*(bank-12+12*math.exp(-bank/12))+.0015*max(bank-100,0)**2
                    if distance < width*.5:
                        t = distance/(width*.5)
                        ceiling = river_level-2.5+2.15*t*t*(3-2*t)
                    if ceiling <= level+.1:
                        return True
            return False
        shore = [(x,z) for x,z in outline if not river_mouth(x,z)]
        require(len(shore) >= len(outline)*.7, 'Insufficient dry shoreline')
        require(all(sample(x, z) > level for x, z in shore), f'Lake shoreline submerged: {lake["name"]}')
        cx = sum(p[0] for p in outline)/len(outline)
        cz = sum(p[1] for p in outline)/len(outline)
        require(sample(cx, cz) < level, f'Lake basin above surface: {lake["name"]}')
    print('PASS: 4 downstream-monotone rivers; 3 flat lakes below dry shorelines (river mouths excluded)')
    placements = json.loads((WORLD/'placements.json').read_text())['placements']
    bridge = next(p for p in placements if p['asset']=='bridge_arch_a')
    c,s = math.cos(bridge['yaw']),math.sin(bridge['yaw'])
    def crossing_height(span, flow):
        return sample(bridge['x']+c*span+s*flow,bridge['z']-s*span+c*flow)
    wet = [crossing_height(span,flow) for span in range(-8,9,2) for flow in range(-3,4)]
    banks = [crossing_height(side*span,flow) for side in [-1,1]
             for span in [13,14,16,18,20.47] for flow in [-3.63,-2,0,2,3.63]]
    require(max(wet)<179.9, 'Bridge inlet is not wet under the opening')
    require(min(banks)>180.075 and max(banks)-min(banks)<.075, 'Bridge landing footprints are not supported by dry, level banks')
    print('PASS: inlet is wet under the bridge; both full landing footprints are dry and supported')
    stair = next(p for p in placements if p['asset']=='stair_terrace_a')
    fixture = json.loads(Path(__file__).with_name('stair_support.json').read_text())
    asset = json.loads((WORLD.parent/'assets/monuments/stair_terrace_a/asset.json').read_text())
    require(fixture['source_sha256']==asset['review']['source_sha256'], 'Stair contact fixture needs regeneration for the new approved source')
    def surface(x,z):
        ix,iz = math.floor(x/2)*2,math.floor(z/2)*2
        u,v = (x-ix)/2,(z-iz)/2
        a,b,c,d = sample(ix,iz),sample(ix+2,iz),sample(ix,iz+2),sample(ix+2,iz+2)
        return a+(b-a)*u+(c-a)*v if u+v<=1 else d+(c-d)*(1-u)+(b-d)*(1-v)
    c,s = math.cos(stair['yaw']),math.sin(stair['yaw'])
    base = surface(stair['x'],stair['z'])+stair.get('y_offset',0)
    burial = [surface(stair['x']+c*x+s*z,stair['z']-s*x+c*z)-base-y
              for x,y,z in fixture['contact_points']]
    require(len(burial)>400 and min(burial)>.015 and max(burial)<.5, 'Stair front apron floats or is deeply buried')
    print(f'PASS: {len(burial)} exported stair contact samples supported; burial {min(burial):.3f}…{max(burial):.3f} m')
    print(f'WORLD OK — height range {low:.2f}…{high:.2f} m; quantization {(high-low)/65535:.4f} m')


if __name__ == '__main__':
    main()
