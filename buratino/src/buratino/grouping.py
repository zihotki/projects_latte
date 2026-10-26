"""Group physical parts by an explicit cutting-blank signature."""

import hashlib
import json


def _signature(part: dict) -> tuple:
    dims = part["finished_mm"]
    return (
        dims["length"],
        dims["width"],
        dims["thickness"],
        part["material"],
        part["grain_direction"],
        part["grain_status"],
        part["edge_treatment"],
    )


def _group_id(signature: tuple) -> str:
    encoded = json.dumps(signature, separators=(",", ":"), ensure_ascii=True)
    return f"cutting.{hashlib.sha256(encoded.encode()).hexdigest()[:16]}"


def _label(parts: list[dict]) -> str:
    roles = {part["role"].rsplit("__", 1)[-1] for part in parts}
    components = {part.get("component") for part in parts if part.get("component")}
    is_drawer_part = any(
        "instance_id" in part or "drawer_index" in part for part in parts
    )
    if is_drawer_part and components and components <= {"side_left", "side_right"}:
        return "Drawer sides"
    if is_drawer_part and components and components <= {"inner_front", "back"}:
        return "Drawer inner fronts and backs"
    if components == {"bottom"} and is_drawer_part:
        return "Drawer bottoms"
    if components == {"face"} and is_drawer_part:
        return "Overlay fronts"
    if components == {"top"}:
        return "Top panels"
    if components == {"bottom"} and not is_drawer_part:
        return "Bottom panels"
    if components == {"back"}:
        return "Drawer backs" if is_drawer_part else "Back panels"
    if components and components <= {"side_left", "side_right"}:
        return "Side panels"
    if components <= {"left_side", "right_side"} and components:
        return "Side panels"
    if components == {"divider"}:
        return "Divider panels"
    if roles == {"left_side", "right_side"}:
        return "Side panels"
    if len(roles) > 1:
        return "Panels"
    labels = {
        "top": "Top panel",
        "bottom": "Bottom panel",
        "back": "Back panel",
        "left_side": "Side panel",
        "right_side": "Side panel",
    }
    role = roles.pop() if roles else parts[0]["role"]
    return labels.get(role, role.replace("_", " ").title())


def group_cutting_blanks(parts: list[dict]) -> list[dict]:
    """Return deterministic cut-list groups while preserving physical part IDs."""
    grouped: dict[tuple, list[dict]] = {}
    for part in parts:
        grouped.setdefault(_signature(part), []).append(part)

    groups = []
    for signature, members in sorted(
        grouped.items(), key=lambda item: (item[0], tuple(p["id"] for p in item[1]))
    ):
        members = sorted(members, key=lambda part: part["id"])
        first = members[0]
        groups.append(
            {
                "id": _group_id(signature),
                "label": _label(members),
                "quantity": sum(part["quantity"] for part in members),
                "finished_mm": dict(first["finished_mm"]),
                "material": first["material"],
                "grain_direction": first["grain_direction"],
                "grain_status": first["grain_status"],
                "edge_treatment": first["edge_treatment"],
                "grouping_scope": "cutting_blank",
                "machining_status": "unverified",
                "members": [part["id"] for part in members],
            }
        )
    return groups
