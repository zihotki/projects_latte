"""Short drawing captions from the recorded machining dimensions."""


def machining_notes(part: dict) -> list[str]:
    notes = []
    mortises = {}
    for cut in part.get("operations", []):
        if cut.get("type") == "mortise" and "kind" not in cut:
            key = tuple(
                cut[name] for name in ("face", "axis", "length", "width", "depth")
            )
            mortises.setdefault(key, []).append(cut)
    for cut in part.get("operations", []):
        kind = cut.get("kind", cut.get("type", ""))
        if "kind" in cut:
            face = (
                cut["target"]
                .replace("thickness", "T")
                .replace("broad_face", "broad face")
            )
            points = cut.get("local_profile_mm", [])
            if kind == "pocket":
                low = [min(point[axis] for point in points) for axis in range(3)]
                high = [max(point[axis] for point in points) for axis in range(3)]
                if cut.get("role") == "bottom_groove":
                    note = (
                        f"Bottom groove: {high[1] - low[1]:g} mm wide × "
                        f"{cut['depth_mm']:g} mm deep; bottom inset {low[1]:g} mm; "
                        f"length {high[0] - low[0]:g} mm from L {low[0]:g} mm"
                    )
                else:
                    note = (
                        f"Pocket: {high[0] - low[0]:g} × {high[1] - low[1]:g} mm; "
                        f"depth {cut['depth_mm']:g} mm; "
                        f"start L {low[0]:g}, W {low[1]:g} mm"
                    )
                notes.append(f"{note}; face {face} (stock L/W/T).")
            elif kind == "edge_bevel":
                notes.append(
                    f"Bevel: {cut['angle_deg']:g}° at {face} edge (stock L/W/T)."
                )
            elif kind == "profile_trim":
                notes.append("Profile cut: follow the dimensioned outline shown.")
            continue
        face = cut.get("face", "")
        frame = "L/W/T" if cut.get("coordinate_frame") == "stock_lwt" else "XYZ"
        uv_names = ("U", "V")
        if frame == "L/W/T":
            normal = "xyz".index(face[0])
            uv_names = tuple("LWT"[i] for i in range(3) if i != normal)
            face = "LWT"[normal] + face[1:]
        suffix = f"; face {face} (stock {frame})."
        if cut.get("role") == "bottom_groove":
            note = (
                f"Bottom groove: {cut['size_v']:g} mm wide × {cut['depth']:g} mm deep; "
                f"bottom inset {cut['v']:g} mm; length {cut['size_u']:g} mm "
                f"from U {cut['u']:g} mm"
            )
        elif cut.get("input_type") == "groove":
            groove = cut["groove"]
            note = (
                f"Groove: {groove['width']:g} mm wide × {cut['depth']:g} mm deep; "
                f"offset {groove['offset']:g} mm from {groove['edge']} edge; "
                f"length {groove['length']:g} mm from {groove['start']:g} mm"
            )
        elif kind == "pocket":
            note = (
                f"Pocket: {cut['size_u']:g} × {cut['size_v']:g} mm; "
                f"depth {cut['depth']:g} mm; start U {cut['u']:g}, V {cut['v']:g} mm"
            )
        elif kind == "bore":
            note = (
                f"Bore: diameter {cut['diameter']:g} mm; depth {cut['depth']:g} mm; "
                f"center U {cut['u']:g}, V {cut['v']:g} mm"
            )
        elif kind == "mortise":
            key = tuple(
                cut[name] for name in ("face", "axis", "length", "width", "depth")
            )
            members = mortises.pop(key, None)
            if members is None:
                continue
            if len(members) == 1:
                centers = (
                    f"center {uv_names[0]} {cut['u']:g}, {uv_names[1]} {cut['v']:g} mm"
                )
            else:
                rows = {}
                for member in members:
                    rows.setdefault(member["u"], []).append(member["v"])
                centers = f"centers {'/'.join(uv_names)} (mm): " + "; ".join(
                    f"{u:g}/(" + ", ".join(f"{v:g}" for v in values) + ")"
                    for u, values in rows.items()
                )
            count = f"Mortises ({len(members)})" if len(members) > 1 else "Mortise"
            note = (
                f"{count}: {cut['length']:g} × {cut['width']:g} mm; "
                f"depth {cut['depth']:g} mm; {centers}; "
                f"length along {uv_names[0 if cut['axis'] == 'u' else 1]}"
            )
        elif kind in {"rabbet", "bevel"}:
            size = (
                f"{cut['width']:g} mm wide × {cut['depth']:g} mm deep"
                if kind == "rabbet"
                else f"legs {cut['leg_a']:g} × {cut['leg_b']:g} mm"
            )
            note = (
                f"{'Rebate' if kind == 'rabbet' else 'Bevel'}: {size}; "
                f"edge {cut['edge']}; length {cut['length']:g} mm "
                f"from {cut['start']:g} mm"
            )
        else:
            continue
        notes.append(note + suffix)
    return list(dict.fromkeys(notes))
