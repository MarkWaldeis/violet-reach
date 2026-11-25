#!/usr/bin/env python3
"""Self-test for tree_rollout_apply.py: synthetic fixtures only, no node, no repo mutation.

Builds throwaway mini-repos in temp dirs and checks the validation, the invariant
diff, the byte-stable serialization and the atomic --write path.  Never touches the
real world/placements.json.
"""
import copy
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tree_rollout_apply as tra  # noqa: E402

FAILURES = []


def expect(name, condition):
    print(("ok   " if condition else "FAIL ") + name)
    if not condition:
        FAILURES.append(name)
    return condition


def run_main(argv):
    """Run tra.main quietly; returns (exit code, captured output)."""
    out = StringIO()
    with redirect_stdout(out):
        code = tra.main(argv)
    return code, out.getvalue()


def tree_placement(seed, asset, scale):
    return {
        "asset": asset,
        "scatter": {
            "seed": seed,
            "count": 1,
            "polygon": [[344.3, 1230], [344.9, 1230.2], [344.5, 1231]],
            "min_spacing": 5,
            "max_slope": 27,
            "min_height_above_water": 8,
            "max_height_above_water": 240,
            "scale": list(scale),
            "align_to_slope": True,
            "surface": "land",
            "path_clearance": 2,
        },
    }


def fixture_document():
    return {
        "placements": [
            {"asset": "boulder_chalk_a", "x": 691.5, "z": 1200.5, "yaw": 0.45, "scale": 1.05,
             "y_offset": -0.82, "pitch": 0.1, "roll": -0.08},
            {"asset": "shrub_copper_a", "scatter": {
                "seed": 5001, "count": 40, "rect": {"minX": 100, "minZ": 100, "maxX": 200, "maxZ": 200},
                "min_spacing": 2, "max_slope": 30, "min_height_above_water": 4, "max_height_above_water": 200,
                "scale": [0.8, 1.2], "align_to_slope": True, "surface": "meadow", "path_clearance": 1}},
            tree_placement(101, "tree_broadleaf_a", [0.82, 1.25]),
            tree_placement(102, "tree_broadleaf_b", [0.82, 1.25]),
            tree_placement(103, "tree_oak_a", [0.95, 1.25]),  # pilot, already conforming
            {**tree_placement(104, "tree_broadleaf_c", [0.82, 1.25])},  # rect variant below
        ],
    }


def fixture_document_rect():
    document = fixture_document()
    scatter = document["placements"][5]["scatter"]
    del scatter["polygon"]
    scatter["rect"] = {"minX": 300, "minZ": 1200, "maxX": 301, "maxZ": 1201}
    return document


def fixture_report():
    changes = [
        {"seed": 101, "placementIndex": 2, "fromAsset": "tree_broadleaf_a", "species": "oak",
         "toAsset": "tree_oak_a", "scaleRange": [0.95, 1.25], "currentScaleRange": [0.82, 1.25],
         "stage": "oak-beech", "fixed": False, "assetChanged": True, "scaleChanged": True},
        {"seed": 102, "placementIndex": 3, "fromAsset": "tree_broadleaf_b", "species": "willow",
         "toAsset": "tree_willow_a", "scaleRange": [0.9, 1.15], "currentScaleRange": [0.82, 1.25],
         "stage": "willow", "fixed": False, "assetChanged": True, "scaleChanged": True},
        {"seed": 103, "placementIndex": 4, "fromAsset": "tree_oak_a", "species": "oak",
         "toAsset": "tree_oak_a", "scaleRange": [0.95, 1.25], "currentScaleRange": [0.95, 1.25],
         "stage": "fixed", "fixed": True, "assetChanged": False, "scaleChanged": False},
        {"seed": 104, "placementIndex": 5, "fromAsset": "tree_broadleaf_c", "species": "ancient",
         "toAsset": "tree_ancient_a", "scaleRange": [1.0, 1.1], "currentScaleRange": [0.82, 1.25],
         "stage": "ancient", "fixed": False, "assetChanged": True, "scaleChanged": True},
    ]
    return {
        "version": 1,
        "deterministic": True,
        "positionCount": 4,
        "counts": {"oak": 2, "beech": 0, "ancient": 1, "willow": 1},
        "warnings": [],
        "changes": changes,
    }


def make_repo(root, document=None):
    document = document if document is not None else fixture_document_rect()
    world = Path(root) / "world"
    world.mkdir(parents=True)
    payload = tra.serialize_document(document)
    (world / "placements.json").write_bytes(payload)
    report_path = Path(root) / "report.json"
    report_path.write_text(json.dumps(fixture_report()), encoding="utf-8")
    return str(world / "placements.json"), str(report_path), payload


def main():
    # 1. report validation accepts the clean fixture
    problems = tra.validate_report(fixture_report(), 4)
    expect("clean report passes validate_report", not problems)

    # 2. happy path: mutations planned, applied, invariants hold
    with tempfile.TemporaryDirectory() as tmp:
        placements_path, report_path, original_payload = make_repo(tmp)
        document, raw = tra.load_placements(placements_path)
        report = tra.load_report(report_path)[0]
        mutations, problems = tra.plan_mutations(document, report)
        expect("happy path plans 4 mutations without problems", len(mutations) == 4 and not problems)
        by_seed = {m["seed"]: m for m in mutations}
        expect("seed 101 becomes oak with oak range",
               by_seed[101]["to_asset"] == "tree_oak_a" and by_seed[101]["scale"] == [0.95, 1.25])
        expect("seed 102 becomes willow with willow range",
               by_seed[102]["to_asset"] == "tree_willow_a" and by_seed[102]["scale"] == [0.9, 1.15])
        expect("seed 104 becomes ancient with ancient range",
               by_seed[104]["to_asset"] == "tree_ancient_a" and by_seed[104]["scale"] == [1.0, 1.1])
        mutated = tra.apply_mutations(document, mutations)
        diffs, invariant_problems = tra.verify_invariants(document, mutated, mutations)
        expect("invariants pass on the happy path", not invariant_problems)
        # 101: asset + scale[0]; 102: asset + scale[0] + scale[1]; 104: asset + scale[0] + scale[1];
        # pilot 103 conforms -> no diff.  Element-level scale paths: 8 total.
        expect("exactly 8 diff paths (3 asset + 5 scale elements)",
               len(diffs) == 8
               and sum(1 for p, _, _ in diffs if p.endswith(".asset")) == 3
               and sum(1 for p, _, _ in diffs if ".scatter.scale" in p) == 5)
        expect("no diff touches the rect/polygon/seeds/constraints",
               all(p.endswith(".asset") or ".scatter.scale" in p for p, _, _ in diffs))
        summary = tra.summarize(mutations)
        expect("summary counts 3 asset swaps, 3 scale updates, 1 conforming pilot",
               summary["asset_changes"] == 3 and summary["scale_changes"] == 3 and summary["conforming"] == 1)

        # 3. serialization is byte-stable for the unmutated document
        expect("serialize_document round-trips the fixture bytes",
               tra.serialize_document(document) == original_payload)

        # 4. dry-run via main writes nothing
        before = Path(placements_path).read_bytes()
        code, out = run_main(["--repo", tmp, "--report", report_path, "--expect-count", "4"])
        expect("dry-run main exits 0", code == 0)
        expect("dry-run leaves the file byte-identical", Path(placements_path).read_bytes() == before)

        # 5. validate-only passes on the clean fixture
        code, out = run_main(["--repo", tmp, "--report", report_path, "--expect-count", "4", "--validate-only"])
        expect("validate-only exits 0 on the clean fixture", code == 0)

        # 6. --write replaces the file atomically and keeps the backup
        backup = str(Path(tmp) / "backup" / "placements-backup.json")
        code, out = run_main(["--repo", tmp, "--report", report_path, "--expect-count", "4", "--write", "--backup", backup])
        expect("--write exits 0", code == 0)
        written_document = json.loads(Path(placements_path).read_bytes().decode("utf-8"))
        placements = written_document["placements"]
        expect("written file: seed 101 is tree_oak_a with oak scale",
               placements[2]["asset"] == "tree_oak_a" and placements[2]["scatter"]["scale"] == [0.95, 1.25])
        expect("written file: seed 102 is tree_willow_a with willow scale",
               placements[3]["asset"] == "tree_willow_a" and placements[3]["scatter"]["scale"] == [0.9, 1.15])
        expect("written file: seed 104 rect entry is tree_ancient_a, rect intact",
               placements[5]["asset"] == "tree_ancient_a"
               and placements[5]["scatter"]["rect"] == {"minX": 300, "minZ": 1200, "maxX": 301, "maxZ": 1201})
        expect("written file: non-tree single placement untouched",
               placements[0] == document["placements"][0])
        expect("written file: non-tree scatter placement untouched",
               placements[1] == document["placements"][1])
        expect("written file: seeds/counts/constraints unchanged on mutated entries",
               all(placements[i]["scatter"]["seed"] == document["placements"][i]["scatter"]["seed"]
                   and placements[i]["scatter"]["count"] == 1
                   and placements[i]["scatter"]["min_spacing"] == 5
                   and placements[i]["scatter"]["max_slope"] == 27
                   and placements[i]["scatter"]["path_clearance"] == 2
                   for i in (2, 3, 5)))
        expect("backup holds the original bytes", Path(backup).read_bytes() == original_payload)
        leftovers = [p for p in (Path(tmp) / "world").iterdir() if p.name != "placements.json"]
        expect("no temp files left behind in world/", not leftovers)
        written_bytes = Path(placements_path).read_bytes()
        expect("written file uses the byte-stable CRLF format",
               written_bytes == tra.serialize_document(written_document) and b"\r\n" in written_bytes)

        # 7. idempotency: applying against the mutated file with a refreshed report is a no-op diff
        refreshed = copy.deepcopy(fixture_report())
        for change in refreshed["changes"]:
            change["fromAsset"] = {"101": "tree_oak_a", "102": "tree_willow_a", "103": "tree_oak_a", "104": "tree_ancient_a"}[str(change["seed"])]
            change["currentScaleRange"] = list(change["scaleRange"])
        refreshed_path = str(Path(tmp) / "report-refreshed.json")
        Path(refreshed_path).write_text(json.dumps(refreshed), encoding="utf-8")
        document2, _ = tra.load_placements(placements_path)
        mutations2, problems2 = tra.plan_mutations(document2, refreshed)
        mutated2 = tra.apply_mutations(document2, mutations2)
        diffs2, inv2 = tra.verify_invariants(document2, mutated2, mutations2)
        expect("second run is a no-op (no diffs, no problems)", not diffs2 and not inv2 and not problems2)

    # 8. stale report detection: wrong fromAsset
    with tempfile.TemporaryDirectory() as tmp:
        placements_path, report_path, _ = make_repo(tmp)
        stale = fixture_report()
        stale["changes"][0]["fromAsset"] = "tree_broadleaf_c"
        stale_path = str(Path(tmp) / "stale.json")
        Path(stale_path).write_text(json.dumps(stale), encoding="utf-8")
        document, _ = tra.load_placements(placements_path)
        _, problems = tra.plan_mutations(document, stale)
        expect("wrong fromAsset is rejected as stale", any("stale" in p and "101" in p for p in problems))
        code, out = run_main(["--repo", tmp, "--report", stale_path, "--expect-count", "4", "--validate-only"])
        expect("validate-only exits 1 on a stale report", code == 1)
        expect("nothing written on invalid input", json.loads(Path(placements_path).read_bytes().decode("utf-8"))["placements"][2]["asset"] == "tree_broadleaf_a")

    # 9. stale report detection: wrong placementIndex
    with tempfile.TemporaryDirectory() as tmp:
        placements_path, report_path, _ = make_repo(tmp)
        stale = fixture_report()
        stale["changes"][1]["placementIndex"] = 99
        document, _ = tra.load_placements(placements_path)
        _, problems = tra.plan_mutations(document, stale)
        expect("wrong placementIndex is rejected", any("placementIndex" in p for p in problems))

    # 10. missing seed in the document
    with tempfile.TemporaryDirectory() as tmp:
        document = fixture_document_rect()
        document["placements"] = [p for p in document["placements"] if p.get("scatter", {}).get("seed") != 104]
        placements_path, report_path, _ = make_repo(tmp, document)
        loaded, _ = tra.load_placements(placements_path)
        _, problems = tra.plan_mutations(loaded, fixture_report())
        expect("report seed without placement is rejected", any("seed 104" in p for p in problems))

    # 11. coverage: rollout tree missing from the report
    with tempfile.TemporaryDirectory() as tmp:
        placements_path, report_path, _ = make_repo(tmp)
        partial = fixture_report()
        partial["changes"] = [c for c in partial["changes"] if c["seed"] != 104]
        partial["positionCount"] = 3
        partial["counts"] = {"oak": 2, "beech": 0, "ancient": 0, "willow": 1}
        loaded, _ = tra.load_placements(placements_path)
        mutations, problems = tra.plan_mutations(loaded, partial)
        expect("uncovered rollout tree placement is rejected", any("missing from the report" in p and "104" in p for p in problems))

    # 12. species table violations in the report
    bad = fixture_report()
    bad["changes"][0]["scaleRange"] = [1.0, 1.0]
    problems = tra.validate_report(bad, 4)
    expect("non-canonical scaleRange is rejected", any("scaleRange" in p for p in problems))
    bad = fixture_report()
    bad["changes"][1]["toAsset"] = "tree_willow_b"
    problems = tra.validate_report(bad, 4)
    expect("non-canonical toAsset is rejected", any("toAsset" in p for p in problems))
    bad = fixture_report()
    bad["changes"][2]["species"] = "birch"
    problems = tra.validate_report(bad, 4)
    expect("unknown species is rejected", any("unknown species" in p for p in problems))
    bad = fixture_report()
    bad["counts"]["oak"] = 99
    problems = tra.validate_report(bad, 4)
    expect("inconsistent report counts are rejected", any("counts.oak" in p for p in problems))

    # 13. duplicate tree seeds in the document
    with tempfile.TemporaryDirectory() as tmp:
        document = fixture_document_rect()
        duplicate = copy.deepcopy(document["placements"][2])
        document["placements"].append(duplicate)
        placements_path, report_path, _ = make_repo(tmp, document)
        loaded, _ = tra.load_placements(placements_path)
        _, problems = tra.plan_mutations(loaded, fixture_report())
        expect("duplicate rollout seeds are rejected", any("duplicate rollout tree seed 101" in p for p in problems))

    # 14. count mismatch against --expect-count
    problems = tra.validate_report(fixture_report(), 360)
    expect("unexpected change count is rejected", any("expected 360" in p for p in problems))

    # 15. invariant violation detection: tampered polygon/seed/count/position
    document = fixture_document_rect()
    report = fixture_report()
    mutations, problems = tra.plan_mutations(document, report)
    base = tra.apply_mutations(document, mutations)
    for label, tamper in [
        ("polygon point moved", lambda m: m["placements"][2]["scatter"]["polygon"][0].__setitem__(0, 999.9)),
        ("seed changed", lambda m: m["placements"][2]["scatter"].__setitem__("seed", 777)),
        ("count changed", lambda m: m["placements"][3]["scatter"].__setitem__("count", 2)),
        ("constraint changed", lambda m: m["placements"][5]["scatter"].__setitem__("max_slope", 12)),
        ("non-tree position moved", lambda m: m["placements"][0].__setitem__("x", 1.5)),
        ("extra placement appended", lambda m: m["placements"].append({"asset": "rogue", "x": 0, "z": 0, "yaw": 0, "scale": 1})),
    ]:
        tampered = copy.deepcopy(base)
        tamper(tampered)
        _, invariant_problems = tra.verify_invariants(document, tampered, mutations)
        expect(f"invariant violation detected: {label}", bool(invariant_problems))

    # 16. wrong target values are caught even on allowed paths
    wrong = copy.deepcopy(base)
    wrong["placements"][2]["asset"] = "tree_willow_a"
    _, invariant_problems = tra.verify_invariants(document, wrong, mutations)
    expect("wrong asset value on an allowed path is rejected", any("tree_willow_a" in p for p in invariant_problems))

    # 17. --write refuses a non-byte-stable file unless --allow-reformat
    with tempfile.TemporaryDirectory() as tmp:
        placements_path, report_path, _ = make_repo(tmp)
        reformatted = json.dumps(fixture_document_rect(), indent=4) + "\n"
        Path(placements_path).write_text(reformatted, encoding="utf-8")
        before = Path(placements_path).read_bytes()
        code, out = run_main(["--repo", tmp, "--report", report_path, "--expect-count", "4", "--write"])
        expect("--write refuses non-byte-stable formatting", code == 1)
        expect("refused write leaves the file untouched", Path(placements_path).read_bytes() == before)
        code, out = run_main(["--repo", tmp, "--report", report_path, "--expect-count", "4", "--write", "--allow-reformat"])
        expect("--write --allow-reformat proceeds", code == 0)

    # 18. diff_documents type strictness and missing keys
    diffs = tra.diff_documents({"a": [1, 2], "b": 1}, {"a": [1], "b": 1.0, "c": 3})
    paths = {p for p, _, _ in diffs}
    expect("diff detects length, type and missing-key differences",
           "a.length" in paths and "b" in paths and "c" in paths)

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} checks failed")
        return 1
    print("PASS: all tree_rollout_apply checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
