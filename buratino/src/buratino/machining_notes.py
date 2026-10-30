"""Short drawing captions from the recorded machining dimensions."""


def machining_notes(part: dict) -> list[str]:
    notes = []
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
        suffix = f"; face {face} (stock XYZ)."
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
            note = (
                f"Mortise: {cut['length']:g} × {cut['width']:g} mm; "
                f"depth {cut['depth']:g} mm; center U {cut['u']:g}, V {cut['v']:g} mm; "
                f"length along {cut['axis'].upper()}"
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
