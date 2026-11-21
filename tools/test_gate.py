#!/usr/bin/env python3
"""Self-test for the Blender gate in vr.py: builds throwaway asset folders and checks each rule."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vr  # noqa: E402


def make(root, **overrides):
    d = os.path.join(root, "props", "thing")
    os.makedirs(os.path.join(d, "review"), exist_ok=True)
    with open(os.path.join(d, "build.py"), "w") as f:
        f.write("def build():\n    pass\n")
    with open(os.path.join(d, "review", "sheet.jpg"), "wb") as f:
        f.write(b"sheet")
    meta = {"id": "thing", "category": "props", "status": "approved", "builder": "session-a",
            "review": {"reviewer": "session-b", "scores": {c: 9 for c in vr.CRITERIA},
                       "source_sha256": vr.source_hash(d),
                       "sheet_sha256": vr.sha256(os.path.join(d, "review", "sheet.jpg"))}}
    meta.update(overrides)
    with open(os.path.join(d, "asset.json"), "w") as f:
        json.dump(meta, f)
    return d, meta


def expect(name, problems, fragment):
    ok = (not problems) if fragment is None else any(fragment in p for p in problems)
    print(("ok   " if ok else "FAIL ") + name)
    return ok


def main():
    results = []
    with tempfile.TemporaryDirectory() as root:
        d, meta = make(root)
        results.append(expect("approved asset passes", vr.gate_problems(d, meta), None))

        d, meta = make(root, status="blender_review")
        results.append(expect("unapproved status is refused", vr.gate_problems(d, meta), "status is"))

        d, meta = make(root, review=None)
        results.append(expect("missing review is refused", vr.gate_problems(d, meta), "no review"))

        d, meta = make(root, builder="session-b")
        results.append(expect("self-review is refused", vr.gate_problems(d, meta), "reviewer is the builder"))

        d, meta = make(root)
        meta["review"]["scores"]["material"] = 7
        results.append(expect("a score below 8 is refused", vr.gate_problems(d, meta), "material=7"))

        d, meta = make(root)
        with open(os.path.join(d, "build.py"), "a") as f:
            f.write("# changed after review\n")
        results.append(expect("build.py edited after review is refused", vr.gate_problems(d, meta), "build.py changed"))

        d, meta = make(root)
        with open(os.path.join(d, "review", "sheet.jpg"), "wb") as f:
            f.write(b"another sheet")
        results.append(expect("swapped review sheet is refused", vr.gate_problems(d, meta), "not the sheet"))
    if not all(results):
        raise SystemExit(1)
    print(f"{len(results)} gate rules hold")


if __name__ == "__main__":
    main()
