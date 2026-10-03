from . import records

TOOL_FILE = "CursorBehaviours.txt"
TOOL_LABEL = "mmoCursorBehaviourVehicle"
TOOL_NAME = "@Travel Vehicle"


def offer_vehicle(existing: str, vehicle: str) -> str:
    parsed = records.parse(existing) if existing else []
    tool = next((r for r in parsed if r.label == TOOL_LABEL and r.prop("name") == TOOL_NAME), None)
    if tool is None:
        tool = records.block(TOOL_LABEL, records.leaf("name", TOOL_NAME, semicolon=False))
        parsed.append(tool)
    line = tool.child("typeNames")
    names = line.texts() if line else []
    if vehicle not in names:
        tool.set_prop("typeNames", *names, vehicle)

    return records.render(parsed)


def vehicle_tool_file(game: str, own: str, vehicle: str, standalone: bool) -> str:
    if not standalone:
        return offer_vehicle(own, vehicle)
    text = game
    for name in [*offered_vehicles(own), vehicle]:
        text = offer_vehicle(text, name)

    return text


def offered_vehicles(text: bytes | str) -> list[str]:
    tool = next((r for r in records.parse(text) if r.label == TOOL_LABEL and r.prop("name") == TOOL_NAME), None)
    line = tool.child("typeNames") if tool else None

    return line.texts() if line else []
