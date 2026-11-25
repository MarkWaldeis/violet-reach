#!/usr/bin/env python3
"""Offline applier for the broadleaf-to-fantasy tree rollout. Standard library only.

  tree_rollout_apply.py                        dry-run: plan mutations, verify invariants, write nothing
  tree_rollout_apply.py --validate-only        compact pass/fail checks, exit 0/1, write nothing
  tree_rollout_apply.py --write                atomically replace world/placements.json and report
  tree_rollout_apply.py --report report.json   read a saved planner report instead of running node
  tree_rollout_apply.py --report -             read the planner report from stdin

The species assignment comes from `node web/explore/scripts/tree-rollout-planner.mjs`
(read-only planner, deterministic).  This script is the only writer and it touches
exactly two fields per count-1 tree placement: `asset` becomes `tree_<species>_a`
and `scatter.scale` becomes the species range:

  oak/beech [0.95, 1.25]   ancient [1.0, 1.1]   willow [0.9, 1.15]

Everything else - seeds, polygons/rects, counts, scatter constraints and every
non-tree placement including its position - must survive unchanged; the invariant
check is a full recursive document diff with an allowlist of the two intended paths.
Without --write nothing is ever written.  There is no --write default and no git
interaction of any kind.
"""
import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANNER = os.path.join("web", "explore", "scripts", "tree-rollout-planner.mjs")
PLACEMENTS_REL = os.path.join("world", "placements.json")

# Canonical species table (mirrors TREE_ASSETS/TREE_SCALE_RANGES in
# web/explore/src/tree-rollout-planner.ts).  The report is validated against this
# table and the table - not the report - supplies the written values.
SPECIES = {
    "oak": {"asset": "tree_oak_a", "scale": [0.95, 1.25]},
    "beech": {"asset": "tree_beech_a", "scale": [0.95, 1.25]},
    "ancient": {"asset": "tree_ancient_a", "scale": [1.0, 1.1]},
    "willow": {"asset": "tree_willow_a", "scale": [0.9, 1.15]},
}
BROADLEAF_ASSETS = {"tree_broadleaf_a", "tree_broadleaf_b", "tree_broadleaf_c"}
FANTASY_ASSETS = {entry["asset"] for entry in SPECIES.values()}
ROLLOUT_ASSETS = BROADLEAF_ASSETS | FANTASY_ASSETS

EXPECTED_TREE_COUNT = 360
DIFF_ASSET_SUFFIX = ".asset"
DIFF_SCALE_SUFFIX = ".scatter.scale"


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def load_placements(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SystemExit(f"{path}: unreadable JSON: {exc}")
    if not isinstance(document, dict) or not isinstance(document.get("placements"), list):
        raise SystemExit(f"{path}: expected an object with a placements array")
    return document, raw


def serialize_document(document):
    """Byte-stable format of world/placements.json: indent 2, CRLF, trailing newline.

    Verified against the committed file: json.loads + this serialization is a
    byte-identical round-trip, so a write produces a minimal line diff.
    """
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    return text.replace("\n", "\r\n").encode("utf-8")


def report_from_planner(repo, node, timeout):
    planner = os.path.join(repo, PLANNER)
    if not os.path.isfile(planner):
        raise SystemExit(f"planner script missing: {planner}")
    command = [node, planner, "--compact", "--repo", repo]
    try:
        proc = subprocess.run(command, cwd=repo, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise SystemExit(f"node executable not found: {node!r}; pass --node or use --report <file>")
    except subprocess.TimeoutExpired:
        raise SystemExit(f"planner timed out after {timeout}s")
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip()[-600:]
        raise SystemExit(f"planner failed with exit code {proc.returncode}: {tail}")
    try:
        return json.loads(proc.stdout.decode("utf-8")), f"subprocess: {' '.join(command)}"
    except (UnicodeDecodeError, ValueError) as exc:
        raise SystemExit(f"planner stdout is not valid JSON: {exc}")


def load_report(path):
    if path == "-":
        try:
            return json.loads(sys.stdin.read()), "stdin"
        except ValueError as exc:
            raise SystemExit(f"stdin is not valid JSON: {exc}")
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        return json.loads(raw.decode("utf-8")), path
    except (UnicodeDecodeError, ValueError) as exc:
        raise SystemExit(f"{path}: unreadable JSON: {exc}")


def validate_report(report, expect_count):
    """Structural and species-table validation of the planner report."""
    problems = []
    if not isinstance(report, dict):
        return ["report is not a JSON object"]
    if report.get("version") != 1:
        problems.append(f"report version {report.get('version')!r}, expected 1")
    changes = report.get("changes")
    if not isinstance(changes, list) or not changes:
        problems.append("report has no non-empty changes array")
        return problems
    if report.get("positionCount") != len(changes):
        problems.append(f"positionCount {report.get('positionCount')!r} != changes length {len(changes)}")
    if len(changes) != expect_count:
        problems.append(f"expected {expect_count} count-1 tree changes, report carries {len(changes)}")

    seeds = set()
    counts = {species: 0 for species in SPECIES}
    for i, change in enumerate(changes):
        label = f"changes[{i}]"
        if not isinstance(change, dict):
            problems.append(f"{label}: not an object")
            continue
        seed = change.get("seed")
        if type(seed) is not int or seed in seeds:
            problems.append(f"{label}: duplicate or non-integer seed {seed!r}")
        else:
            seeds.add(seed)
        if type(change.get("placementIndex")) is not int:
            problems.append(f"{label}: placementIndex is not an integer")
        species = change.get("species")
        if species not in SPECIES:
            problems.append(f"{label}: unknown species {species!r}")
            continue
        counts[species] += 1
        canonical = SPECIES[species]
        if change.get("toAsset") != canonical["asset"]:
            problems.append(f"{label}: toAsset {change.get('toAsset')!r} != canonical {canonical['asset']!r}")
        scale = change.get("scaleRange")
        if not (isinstance(scale, list) and len(scale) == 2 and scale[0] == canonical["scale"][0] and scale[1] == canonical["scale"][1]):
            problems.append(f"{label}: scaleRange {scale!r} != canonical {canonical['scale']!r}")
        if not isinstance(change.get("fromAsset"), str) or change["fromAsset"] not in ROLLOUT_ASSETS:
            problems.append(f"{label}: fromAsset {change.get('fromAsset')!r} is not a rollout tree asset")

    report_counts = report.get("counts")
    if isinstance(report_counts, dict):
        for species, count in counts.items():
            if report_counts.get(species) != count:
                problems.append(f"report counts.{species} {report_counts.get(species)!r} != aggregated changes {count}")
    return problems


def plan_mutations(document, report):
    """Match every report change to its placement by seed and cross-check index/asset.

    Returns (mutations, problems).  A mutation is
    {seed, index, species, to_asset, scale, from_asset, fixed, stage}.
    """
    placements = document["placements"]
    by_seed = {}
    problems = []
    for index, placement in enumerate(placements):
        if not isinstance(placement, dict) or not isinstance(placement.get("scatter"), dict):
            continue
        seed = placement["scatter"].get("seed")
        if placement.get("asset") in ROLLOUT_ASSETS:
            if seed in by_seed:
                problems.append(f"duplicate rollout tree seed {seed} in placements [{by_seed[seed]}] and [{index}]")
            by_seed.setdefault(seed, index)

    mutations = []
    covered = set()
    for change in report["changes"]:
        seed = change.get("seed")
        if type(seed) is not int:
            continue  # already reported by validate_report
        index = by_seed.get(seed)
        if index is None:
            problems.append(f"seed {seed}: no rollout tree placement in the document")
            continue
        placement = placements[index]
        if change.get("placementIndex") != index:
            problems.append(f"seed {seed}: report placementIndex {change.get('placementIndex')} != document index {index} (stale report?)")
        if placement.get("asset") != change.get("fromAsset"):
            problems.append(f"seed {seed}: document asset {placement.get('asset')!r} != report fromAsset {change.get('fromAsset')!r} (stale report?)")
        scatter = placement["scatter"]
        if scatter.get("count") != 1:
            problems.append(f"seed {seed}: scatter.count {scatter.get('count')!r} != 1")
        species = change.get("species")
        if species not in SPECIES:
            continue  # already reported
        canonical = SPECIES[species]
        mutations.append({
            "seed": seed,
            "index": index,
            "species": species,
            "to_asset": canonical["asset"],
            "scale": list(canonical["scale"]),
            "from_asset": placement.get("asset"),
            "from_scale": list(scatter.get("scale", [])) if isinstance(scatter.get("scale"), list) else None,
            "fixed": bool(change.get("fixed")),
            "stage": change.get("stage"),
        })
        covered.add(index)

    for index, placement in enumerate(placements):
        if index in covered or not isinstance(placement, dict):
            continue
        if placement.get("asset") in ROLLOUT_ASSETS and isinstance(placement.get("scatter"), dict):
            seed = placement["scatter"].get("seed")
            problems.append(f"placements[{index}] seed {seed}: rollout tree asset {placement['asset']!r} is missing from the report")
    return mutations, problems


def apply_mutations(document, mutations):
    """Return a deep-copied document with exactly asset + scatter.scale replaced."""
    mutated = copy.deepcopy(document)
    for mutation in mutations:
        placement = mutated["placements"][mutation["index"]]
        placement["asset"] = mutation["to_asset"]
        placement["scatter"]["scale"] = list(mutation["scale"])
    return mutated


def diff_documents(original, mutated, prefix=""):
    """Recursive (path, old, new) diff; numbers compare with ==, missing keys as <missing>."""
    missing = object()
    diffs = []

    def walk(a, b, path):
        if type(a) is dict and type(b) is dict:
            for key in sorted(set(a) | set(b), key=str):
                walk(a.get(key, missing), b.get(key, missing), f"{path}.{key}" if path else str(key))
        elif type(a) is list and type(b) is list:
            if len(a) != len(b):
                diffs.append((f"{path}.length" if path else "length", len(a), len(b)))
            for i in range(min(len(a), len(b))):
                walk(a[i], b[i], f"{path}[{i}]")
        elif a is missing or b is missing:
            diffs.append((path, "<missing>" if a is missing else a, "<missing>" if b is missing else b))
        elif a != b or type(a) is not type(b):
            diffs.append((path, a, b))

    walk(original, mutated, prefix)
    return diffs


def verify_invariants(document, mutated, mutations):
    """The only tolerated differences are .asset and .scatter.scale of mutated placements.

    This single allowlist check covers every invariant at once: seeds, polygons/rects,
    counts, scatter constraints (min_spacing, max_slope, height window, surface,
    align_to_slope, path_clearance), single-placement positions (x/z/yaw/scale) and
    every non-tree placement.  Positions of the trees themselves are not stored -
    they derive deterministically from seed+polygon+constraints, which are verified
    unchanged here.
    """
    def allowlisted(path):
        for mutation in mutations:
            base = f"placements[{mutation['index']}]"
            if path == base + DIFF_ASSET_SUFFIX:
                return True
            scale_path = base + DIFF_SCALE_SUFFIX
            if path == scale_path or path.startswith(scale_path + "["):
                return True
        return False

    diffs = diff_documents(document, mutated)
    problems = []
    for path, old, new in diffs:
        if not allowlisted(path):
            problems.append(f"invariant violation at {path}: {old!r} -> {new!r}")
    # Independent of the diff granularity, the landed values must be the canonical ones.
    for mutation in mutations:
        placement = mutated["placements"][mutation["index"]]
        if placement.get("asset") != mutation["to_asset"]:
            problems.append(f"placements[{mutation['index']}].asset is {placement.get('asset')!r}, expected {mutation['to_asset']!r}")
        scale = placement.get("scatter", {}).get("scale")
        if not isinstance(scale, list) or scale != mutation["scale"]:
            problems.append(f"placements[{mutation['index']}].scatter.scale is {scale!r}, expected {mutation['scale']!r}")
    return diffs, problems


def atomic_write(path, payload, backup=None):
    """Write payload to a temp file in the same directory, fsync, then os.replace.

    Same-directory + os.replace keeps the rename atomic on the same volume on both
    NTFS and POSIX.  The temp file is removed if anything fails before the replace.
    """
    directory = os.path.dirname(os.path.abspath(path))
    if backup:
        with open(path, "rb") as handle:
            original = handle.read()
        backup_dir = os.path.dirname(os.path.abspath(backup))
        os.makedirs(backup_dir, exist_ok=True)
        with open(backup, "wb") as handle:
            handle.write(original)
    fd, temp_path = tempfile.mkstemp(prefix=".placements.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # Verify the payload parses before it may replace anything.
        with open(temp_path, "rb") as handle:
            json.loads(handle.read().decode("utf-8"))
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return temp_path


def summarize(mutations):
    per_species = {species: 0 for species in SPECIES}
    asset_changes = scale_changes = fixed = conforming = 0
    for mutation in mutations:
        per_species[mutation["species"]] += 1
        asset_same = mutation["from_asset"] == mutation["to_asset"]
        scale_same = mutation["from_scale"] == mutation["scale"]
        asset_changes += int(not asset_same)
        scale_changes += int(not scale_same)
        conforming += int(asset_same and scale_same)
        fixed += int(mutation["fixed"])
    return {
        "per_species": per_species,
        "asset_changes": asset_changes,
        "scale_changes": scale_changes,
        "fixed": fixed,
        "conforming": conforming,
    }


def build(repo, report, expect_count):
    """Validate inputs, plan + simulate the mutation, verify invariants.  Purely in-memory."""
    placements_path = os.path.join(repo, PLACEMENTS_REL)
    if not os.path.isfile(placements_path):
        raise SystemExit(f"missing {placements_path}")
    document, original_bytes = load_placements(placements_path)

    report_problems = validate_report(report, expect_count)
    mutations = []
    match_problems = []
    diffs = []
    invariant_problems = []
    if not report_problems:
        mutations, match_problems = plan_mutations(document, report)
    mutated = None
    payload = None
    format_stable = None
    if not report_problems and not match_problems:
        mutated = apply_mutations(document, mutations)
        diffs, invariant_problems = verify_invariants(document, mutated, mutations)
        payload = serialize_document(mutated)
        format_stable = serialize_document(document) == original_bytes
    return {
        "placements_path": placements_path,
        "document": document,
        "original_bytes": original_bytes,
        "report_problems": report_problems,
        "match_problems": match_problems,
        "problems": report_problems + match_problems,
        "mutations": mutations,
        "mutated": mutated,
        "diffs": diffs,
        "invariant_problems": invariant_problems,
        "payload": payload,
        "format_stable": format_stable,
    }


def print_report(state, report, report_source, mode, diff_limit=12):
    mutations = state["mutations"]
    summary = summarize(mutations)
    print(f"tree-rollout apply - {mode}")
    print(f"  report: {report_source} (version {report.get('version')}, deterministic {report.get('deterministic')})")
    print(f"  placements: {state['placements_path']} ({len(state['document']['placements'])} entries, sha256 {sha256_bytes(state['original_bytes'])[:16]})")
    species_text = ", ".join(f"{species} {summary['per_species'][species]}" for species in SPECIES)
    print(f"  mutations: {len(mutations)} count-1 tree placements ({species_text})")
    print(f"  effective edits: {summary['asset_changes']} asset swaps, {summary['scale_changes']} scale-range updates; {summary['conforming']} entries already conform; fixed pilot assignments: {summary['fixed']}")
    effective = [m for m in mutations if m["from_asset"] != m["to_asset"] or m["from_scale"] != m["scale"]]
    if not effective:
        print("  no effective edits: every placement already carries the target asset+scale")
    for mutation in effective[:diff_limit]:
        fixed_tag = " [fixed pilot]" if mutation["fixed"] else ""
        print(f"    seed {mutation['seed']} idx {mutation['index']}: {mutation['from_asset']} -> {mutation['to_asset']}, scale {mutation['from_scale']} -> {mutation['scale']}{fixed_tag}")
    if len(effective) > diff_limit:
        print(f"    ... {len(effective) - diff_limit} more")
    warnings = report.get("warnings") or []
    for warning in warnings:
        print(f"  planner warning: {warning}")
    print(f"  invariants: {'PASS' if not state['invariant_problems'] else 'FAIL'} - recursive document diff; only .asset/.scatter.scale of the {len(mutations)} tree placements may differ")
    print(f"  diff paths: {len(state['diffs'])} (asset {sum(1 for p, _, _ in state['diffs'] if p.endswith(DIFF_ASSET_SUFFIX))}, scale {sum(1 for p, _, _ in state['diffs'] if DIFF_SCALE_SUFFIX in p)})")
    if state["format_stable"] is not None:
        print(f"  serialization: {'byte-stable round-trip confirmed (indent 2, CRLF, trailing newline)' if state['format_stable'] else 'NOT byte-stable - a write would reformat the whole file'}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=ROOT, help="repository root (default: parent of this tools folder)")
    parser.add_argument("--report", help="planner report JSON path, '-' for stdin; default: run the node planner")
    parser.add_argument("--node", default="node", help="node executable for the planner subprocess")
    parser.add_argument("--timeout", type=int, default=180, help="planner subprocess timeout in seconds")
    parser.add_argument("--expect-count", type=int, default=EXPECTED_TREE_COUNT,
                        help=f"expected number of count-1 tree placements (default {EXPECTED_TREE_COUNT})")
    parser.add_argument("--validate-only", action="store_true",
                        help="compact pass/fail validation of report+document+invariants; never writes; exit 0 only if everything passes")
    parser.add_argument("--write", action="store_true",
                        help="atomically replace world/placements.json (temp file + fsync + os.replace); without it this is always a dry-run")
    parser.add_argument("--backup", help="optional path receiving a copy of the original placements.json before --write")
    parser.add_argument("--allow-reformat", action="store_true",
                        help="permit --write even if serialization is not byte-stable for unchanged content")
    args = parser.parse_args(argv)
    if args.backup and not args.write:
        print("note: --backup without --write has no effect (nothing is written)")

    repo = os.path.abspath(args.repo)
    if args.report:
        report, report_source = load_report(args.report)
    else:
        report, report_source = report_from_planner(repo, args.node, args.timeout)

    state = build(repo, report, args.expect_count)

    if args.validate_only:
        checks = []
        checks.append(("report structure + species table", not state["report_problems"]))
        checks.append(("mutation matching (seeds/index/fromAsset/count/coverage)", not state["match_problems"]))
        if not state["problems"]:
            checks.append(("invariants: seeds/polygons/counts/constraints/positions unchanged", not state["invariant_problems"]))
            checks.append((f"expected count {args.expect_count}", len(state["mutations"]) == args.expect_count))
            checks.append(("byte-stable serialization", bool(state["format_stable"])))
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'} {name}")
        for problem in (state["problems"] + state["invariant_problems"])[:20]:
            print(f"  problem: {problem}")
        return 0 if all(ok for _, ok in checks) else 1

    if state["problems"]:
        print("tree-rollout apply - INPUT INVALID, nothing written")
        for problem in state["problems"][:40]:
            print(f"  problem: {problem}")
        if len(state["problems"]) > 40:
            print(f"  ... {len(state['problems']) - 40} more")
        return 1
    if state["invariant_problems"]:
        print("tree-rollout apply - INVARIANT VIOLATION, nothing written")
        for problem in state["invariant_problems"][:40]:
            print(f"  violation: {problem}")
        return 1

    if not args.write:
        print_report(state, report, report_source, "DRY-RUN (nothing written; pass --write to apply)")
        return 0

    if not state["format_stable"] and not args.allow_reformat:
        print("tree-rollout apply - REFUSED: serialization is not byte-stable for unchanged content;")
        print("  a write would reformat the whole file. Pass --allow-reformat if that is acceptable.")
        return 1

    summary = summarize(state["mutations"])
    original_hash = sha256_bytes(state["original_bytes"])
    atomic_write(state["placements_path"], state["payload"], backup=args.backup)
    with open(state["placements_path"], "rb") as handle:
        written = handle.read()
    if written != state["payload"]:
        print("tree-rollout apply - WRITE VERIFICATION FAILED: file content differs from the payload")
        return 1
    species_text = ", ".join(f"{species} {summary['per_species'][species]}" for species in SPECIES)
    print("tree-rollout apply - WRITTEN")
    print(f"  file: {state['placements_path']}")
    print(f"  sha256: {original_hash[:16]} -> {sha256_bytes(written)[:16]}")
    print(f"  changed: {len(state['mutations'])} count-1 tree placements ({species_text}); {summary['asset_changes']} asset swaps, {summary['scale_changes']} scale-range updates")
    print(f"  diff paths: {len(state['diffs'])}; invariants PASS; everything else byte-identical")
    if args.backup:
        print(f"  backup of the original: {args.backup}")
    print("  next: python tools/vr.py check  (gate must stay green)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
