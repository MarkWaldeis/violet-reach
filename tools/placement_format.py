"""Placement shape validation; asset approval remains vr.py's responsibility."""
import math


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def placement_problems(document):
    if not isinstance(document, dict) or not isinstance(document.get("placements"), list):
        return ["expected placements array"]
    errors = []
    for i, p in enumerate(document["placements"]):
        valid = isinstance(p, dict) and isinstance(p.get("asset"), str) and bool(p["asset"])
        if valid and "scatter" not in p:
            valid = all(number(p.get(k)) for k in ("x", "z", "yaw", "scale")) and p["scale"] > 0
            valid = valid and number(p.get("y_offset", 0))
        elif valid:
            s = p["scatter"]
            valid = isinstance(s, dict) and not any(k in p for k in ("x", "z", "yaw", "scale", "y_offset"))
            if valid:
                valid = (type(s.get("seed")) is int and 0 <= s["seed"] <= 4294967295
                         and type(s.get("count")) is int and 0 <= s["count"] <= 1000000
                         and all(number(s.get(k)) for k in ("min_spacing", "max_slope", "min_height_above_water", "max_height_above_water")))
            if valid:
                scale = s.get("scale")
                valid = (s["min_spacing"] >= 0 and 0 <= s["max_slope"] <= 90
                         and s["min_height_above_water"] <= s["max_height_above_water"]
                         and isinstance(scale, list) and len(scale) == 2 and all(number(v) for v in scale)
                         and 0 < scale[0] <= scale[1] and type(s.get("align_to_slope", False)) is bool)
                valid = (valid and s.get("surface", "meadow") in ("meadow", "land", "shore")
                         and number(s.get("path_clearance", 0.5)) and s.get("path_clearance", 0.5) >= 0)
            if valid:
                rect, poly = s.get("rect"), s.get("polygon")
                if (rect is None) == (poly is None):
                    valid = False
                elif rect is not None:
                    valid = (isinstance(rect, dict) and all(number(rect.get(k)) for k in ("minX", "minZ", "maxX", "maxZ"))
                             and rect["minX"] < rect["maxX"] and rect["minZ"] < rect["maxZ"])
                else:
                    valid = (isinstance(poly, list) and len(poly) >= 3
                             and all(isinstance(p, list) and len(p) == 2 and all(number(v) for v in p) for p in poly))
                    if valid:
                        valid = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))) > 0
        if not valid:
            errors.append(f"placement {i}: invalid single/scatter fields")
    return errors
