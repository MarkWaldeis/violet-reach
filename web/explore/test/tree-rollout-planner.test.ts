import assert from "node:assert/strict";
import { test } from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { waterSample, type Hydrology } from "../src/hydrology.ts";
import {
  createDetailedWaterSampler,
  planTreeRollout,
  TREE_SCALE_RANGES,
  type TreeRolloutPositionInput,
  type TreeSpecies,
} from "../src/tree-rollout-planner.ts";
import { buildDryRunReport } from "../scripts/tree-rollout-planner.mjs";

const noFixed = {};
const farWater = { waterDistance: 100, heightAboveWater: 50, corridorId: "test:far:0", waterFeature: "test" };

function position(seed: number, x: number, z: number, water: Partial<TreeRolloutPositionInput> = {}): TreeRolloutPositionInput {
  return {
    seed,
    x,
    z,
    waterDistance: farWater.waterDistance,
    heightAboveWater: farWater.heightAboveWater,
    corridorId: farWater.corridorId,
    waterFeature: farWater.waterFeature,
    asset: "tree_broadleaf_a",
    ...water,
  };
}

function plan(positions: TreeRolloutPositionInput[], targetCounts: Record<TreeSpecies, number>, fixedAssignments: Readonly<Record<number, TreeSpecies>> = noFixed) {
  return planTreeRollout(positions, { targetCounts, fixedAssignments });
}

test("detailed water sampling exactly matches the runtime waterSample numerics and adds stable corridors", () => {
  const hydrology: Hydrology = {
    lakes: [
      { name: "Spiegelsee", water_y: 180, outline: [[0, 0], [80, 0], [80, 60], [40, 35], [0, 60]] },
      { name: "Weiher", water_y: 200, outline: [[200, 0], [240, 0], [240, 40], [200, 40]] },
    ],
    rivers: [
      { name: "Weißfall", polyline: [[-20, 90, 190, 8], [120, 40, 180, 16], [180, 10, 180, 10]] },
      { name: "Punkt", polyline: [[300, 300, 100, 2], [300, 300, 100, 2]] },
    ],
  };
  const detailed = createDetailedWaterSampler(hydrology, 40);
  const segments = hydrology.rivers.flatMap((river) => river.polyline.slice(1).map((b, index) => ({ a: river.polyline[index], b })));
  for (let x = -40; x <= 340; x += 17.3) {
    for (let z = -30; z <= 340; z += 13.7) {
      const expected = waterSample({ lakes: hydrology.lakes, segments }, x, z);
      const actual = detailed(x, z);
      assert.equal(actual.distance, expected.distance);
      assert.equal(actual.height, expected.height);
      assert.equal(actual.lakeDistance, expected.lakeDistance);
      assert.match(actual.corridorId, /^(lake|river):/);
    }
  }
  assert.equal(createDetailedWaterSampler({ lakes: [], rivers: [] })(0, 0).corridorId, "none");
});

test("planner output is byte-deterministic for the same input", () => {
  const positions = [
    position(1, 0, 0), position(2, 6, 0), position(3, 12, 0), position(4, 18, 0),
    position(5, 100, 0), position(6, 106, 0), position(7, 112, 0), position(8, 118, 0),
  ];
  const targets = { oak: 4, beech: 4, ancient: 0, willow: 0 };
  const first = plan(positions, targets);
  const second = plan(positions, targets);
  assert.deepEqual(second, first);
  assert.equal(JSON.stringify(second), JSON.stringify(first));
});

test("willow selection is corridor/cluster stratified instead of taking only the globally nearest trees", () => {
  const near = { waterDistance: 5, heightAboveWater: 9 };
  const mid = { waterDistance: 8, heightAboveWater: 9 };
  const far = { waterDistance: 15, heightAboveWater: 9 };
  const positions = [
    position(1, 0, 0, { ...near, corridorId: "river:near:0" }),
    position(2, 5, 0, { ...near, corridorId: "river:near:0" }),
    position(3, 10, 0, { ...near, corridorId: "river:near:0" }),
    position(4, 100, 0, { ...mid, corridorId: "river:mid:0" }),
    position(5, 105, 0, { ...mid, corridorId: "river:mid:0" }),
    position(6, 110, 0, { ...mid, corridorId: "river:mid:0" }),
    position(7, 200, 0, { ...far, corridorId: "river:far:0" }),
    position(8, 205, 0, { ...far, corridorId: "river:far:0" }),
    position(9, 210, 0, { ...far, corridorId: "river:far:0" }),
    position(10, 400, 0), position(11, 500, 0), position(12, 600, 0),
  ];
  const report = plan(positions, { oak: 4, beech: 3, ancient: 1, willow: 4 });
  assert.equal(report.willow.selectedCount, 4);
  assert.equal(report.willow.shortfall, 0);
  assert.equal(Object.keys(report.willow.selectedByCorridor).length, 3);
  for (const corridor of ["river:near:0", "river:mid:0", "river:far:0"]) assert.ok(report.willow.selectedByCorridor[corridor] >= 1);
  const selected = new Set(report.willow.selectedSeeds);
  assert.ok(!(selected.has(1) && selected.has(2) && selected.has(3) && selected.has(4)), "unstratified nearest-first selection would be dominated by the nearest cluster");
});

test("willow eligibility uses both exact rule branches and never fills inland shortfalls", () => {
  const positions = [
    position(1, 0, 0, { waterDistance: 29.9, heightAboveWater: 30 }),
    position(2, 100, 0, { waterDistance: 54.9, heightAboveWater: 20 }),
    position(3, 200, 0, { waterDistance: 54.9, heightAboveWater: 20.1 }),
    position(4, 300, 0, { waterDistance: 30.1, heightAboveWater: 20.1 }),
    position(5, 400, 0), position(6, 500, 0), position(7, 600, 0), position(8, 700, 0),
    position(9, 800, 0), position(10, 900, 0), position(11, 1000, 0), position(12, 1100, 0),
  ];
  const report = plan(positions, { oak: 4, beech: 2, ancient: 2, willow: 4 });
  assert.deepEqual(report.willow.eligibleSeeds, [1, 2]);
  assert.equal(report.willow.selectedCount, 2);
  assert.equal(report.willow.shortfall, 2);
  assert.equal(report.counts.willow, 2);
  assert.equal(report.counts.oak, 5);
  assert.equal(report.counts.beech, 3);
  assert.equal(report.shortfalls.redistributedToOakBeech.oak, 1);
  assert.equal(report.shortfalls.redistributedToOakBeech.beech, 1);
  assert.ok(report.warnings.some((warning) => warning.includes("willow shortfall 2")));
});

test("ancient selection uses the first feasible spacing step and never violates the hard minimum", () => {
  const positions = [0, 20, 40, 60, 80].map((x, index) => position(index + 1, x, 0));
  const report = plan(positions, { oak: 2, beech: 1, ancient: 2, willow: 0 });
  assert.equal(report.ancient.spacingUsed, 45);
  assert.equal(report.ancient.shortfall, 0);
  assert.ok(report.ancient.minPairSpacing >= 45);
  assert.equal(report.counts.ancient, 2);
});

test("ancient shortfall is exact when the spacing-independent-set capacity is smaller than the quota", () => {
  const positions = [
    position(1, 0, 0), position(2, 10, 0), position(3, 0, 10), position(4, 10, 10),
  ];
  const report = plan(positions, { oak: 1, beech: 1, ancient: 2, willow: 0 });
  assert.equal(report.ancient.spacingUsed, 30);
  assert.equal(report.ancient.spacingSteps.at(-1).maxSelectableAdditional, 1);
  assert.equal(report.counts.ancient, 1);
  assert.equal(report.ancient.shortfall, 1);
  assert.equal(report.ancient.minPairSpacing, null);
  assert.ok(report.warnings.some((warning) => warning.includes("ancient shortfall 1")));
});

test("fixed seeds remain fixed and unfixed pilot seeds enter the normal species pool", () => {
  const positions = [
    position(24144, 0, 0), position(24145, 20, 0), position(24146, 40, 0), position(24157, 100, 0),
  ];
  const fixed = { 24144: "oak" as const, 24157: "beech" as const };
  const report = plan(positions, { oak: 2, beech: 2, ancient: 0, willow: 0 }, fixed);
  assert.equal(report.seedSpecies["24144"], "oak");
  assert.equal(report.seedSpecies["24157"], "beech");
  assert.ok(["oak", "beech"].includes(report.seedSpecies["24145"]));
  assert.ok(["oak", "beech"].includes(report.seedSpecies["24146"]));
  assert.equal(report.positions.find((entry) => entry.seed === 24144).fixed, true);
  assert.equal(report.positions.find((entry) => entry.seed === 24145).fixed, false);
});

test("oak and beech are interleaved inside every multi-slot grove instead of allowing monospecific groves", () => {
  const positions = [
    position(1, 0, 0), position(2, 5, 0), position(3, 10, 0), position(4, 15, 0),
    position(5, 100, 0), position(6, 105, 0), position(7, 110, 0), position(8, 115, 0),
  ];
  const report = plan(positions, { oak: 4, beech: 4, ancient: 0, willow: 0 });
  const firstGrove = positions.slice(0, 4).map((entry) => report.seedSpecies[String(entry.seed)]);
  const secondGrove = positions.slice(4).map((entry) => report.seedSpecies[String(entry.seed)]);
  for (const grove of [firstGrove, secondGrove]) {
    assert.ok(grove.includes("oak"));
    assert.ok(grove.includes("beech"));
  }
  assert.equal(report.counts.oak, 4);
  assert.equal(report.counts.beech, 4);
});

test("all rollout species use the mandated scale ranges", () => {
  const positions = [
    position(1, 0, 0, { waterDistance: 10, heightAboveWater: 10 }),
    position(2, 100, 0), position(3, 200, 0), position(4, 300, 0),
  ];
  const report = plan(positions, { oak: 1, beech: 1, ancient: 1, willow: 1 });
  assert.deepEqual(report.counts, { oak: 1, beech: 1, ancient: 1, willow: 1 });
  for (const entry of report.positions) assert.deepEqual(entry.scaleRange, TREE_SCALE_RANGES[entry.species]);
});

test("current world regression: 360 positions, fixed pilot remap, distributed willows and hard ancient-spacing shortfall", () => {
  const repo = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
  const report = buildDryRunReport(repo);
  assert.equal(report.positionCount, 360);
  assert.deepEqual(report.sourceCounts, { total: 360, broadleaf: 351, pilotFantasy: 9, other: 0 });
  assert.equal(new Set(Object.keys(report.seedSpecies)).size, 360);
  assert.equal(report.seedSpecies["24144"], "oak");
  assert.equal(report.seedSpecies["24148"], "oak");
  assert.equal(report.seedSpecies["24149"], "oak");
  assert.equal(report.seedSpecies["24157"], "ancient");
  assert.equal(report.seedSpecies["24147"], "beech");
  assert.equal(report.seedSpecies["24154"], "beech");
  assert.equal(report.seedSpecies["24158"], "oak");
  assert.notEqual(report.seedSpecies["24145"], "willow");
  assert.notEqual(report.seedSpecies["24146"], "willow");
  assert.equal(report.willow.eligibleCount, 122);
  assert.equal(report.willow.selectedCount, 54);
  assert.equal(report.willow.shortfall, 0);
  assert.ok(Object.keys(report.willow.selectedByCorridor).length >= 7);
  assert.equal(report.ancient.spacingSteps.at(-1).maxSelectableAdditional, 43);
  assert.equal(report.ancient.selectedCount, 44);
  assert.equal(report.ancient.shortfall, 10);
  assert.ok(report.ancient.minPairSpacing >= 30);
  assert.deepEqual(report.counts, { oak: 150, beech: 112, ancient: 44, willow: 54 });
  assert.ok(!report.warnings.some((warning) => warning.includes("oak/beech counts differ")));
  for (const cluster of Object.values(report.clusters)) {
    if (cluster.oak + cluster.beech >= 2) assert.ok(cluster.oak > 0 && cluster.beech > 0, `monospecific oak/beech grove: ${JSON.stringify(cluster)}`);
  }
});
