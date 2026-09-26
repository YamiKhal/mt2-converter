from dataclasses import dataclass, field

from . import records

FPS = 24.0
PLAYBACK_TYPES = ("Once", "OnceAndHold", "Loop", "PingPong")

Key = tuple[float, tuple[float, ...]]

CHANNELS = (
    ("translateKeyframe", "mmoTranslateKeyframe", "translation"),
    ("rotateKeyframe", "mmoRotateKeyframe", "rotation"),
    ("scaleKeyframe", "mmoScaleKeyframe", "scale"),
)


@dataclass
class Timeline:
    node: str
    translation: list[Key] = field(default_factory=list)
    rotation: list[Key] = field(default_factory=list)
    scale: list[Key] = field(default_factory=list)


@dataclass
class Animation:
    name: str
    playback: str = "Once"
    timelines: list[Timeline] = field(default_factory=list)


def read_animations(text: bytes | str) -> list[Animation]:
    return [_read_animation(r) for r in records.parse(text) if r.label == "mmoAnimation"]


def _read_animation(record: records.Record) -> Animation:
    animation = Animation(record.prop("name") or "", record.prop("playbackType") or "Once")
    timeline_block = record.child("timeline")
    for node in timeline_block.children_named("mmoAnimationNodeTimeline") if timeline_block else []:
        timeline = Timeline(node.prop("nodeName") or "")
        for block, entry, value in CHANNELS:
            keys = node.child(block)
            for key in keys.children_named(entry) if keys else []:
                time = key.child("time")
                values = key.child(value)
                if time and values:
                    getattr(timeline, value).append((time.floats()[0], tuple(values.floats())))
        animation.timelines.append(timeline)

    return animation


def write_animations(animations: list[Animation]) -> str:
    return records.render([_animation_record(a) for a in animations])


def _animation_record(animation: Animation) -> records.Record:
    timelines = []
    for timeline in animation.timelines:
        channels = []
        for block, entry, value in CHANNELS:
            keys = getattr(timeline, value)
            if keys:
                channels.append(records.block(block, *[
                    records.block(entry,
                                  records.Record("time", records.vector_line([time], semicolon=False).tokens,
                                                 line_open=False),
                                  records.Record(value, records.vector_line(values, semicolon=False).tokens,
                                                 line_open=False))
                    for time, values in keys
                ]))
        timelines.append(records.block("mmoAnimationNodeTimeline",
                                       records.leaf("nodeName", timeline.node, semicolon=False), *channels))

    return records.block(
        "mmoAnimation",
        records.leaf("name", animation.name, semicolon=False),
        records.leaf("playbackType", animation.playback, quoted=False, semicolon=False),
        records.block("timeline", *timelines),
    )


DOOR_SEQUENCE = (("unlock", "open"), ("open", "close"), ("close", "open"))


def pose_jumps(before: Animation, after: Animation) -> dict[str, tuple[float, float, float]]:
    starts = {t.node: t for t in after.timelines}
    jumps = {}
    for timeline in before.timelines:
        following = starts.get(timeline.node)
        if following is not None:
            jumps[timeline.node] = tuple(_gap(getattr(timeline, channel), getattr(following, channel), channel)
                                         for channel in ("translation", "rotation", "scale"))

    return jumps


def _gap(ending: list[Key], starting: list[Key], channel: str) -> float:
    if not ending or not starting:
        return 0.0
    a, b = ending[-1][1], starting[0][1]
    gap = max(abs(x - y) for x, y in zip(a, b))
    if channel == "rotation":
        gap = min(gap, max(abs(x + y) for x, y in zip(a, b)))

    return gap


def door_order(names) -> list[str]:
    order = [DOOR_SEQUENCE[0][0], *(then for _, then in DOOR_SEQUENCE)]

    return [name for name in order if name in names]


def length(animation: Animation) -> float:
    times = [time for t in animation.timelines for channel in (t.translation, t.rotation, t.scale) for time, _ in channel]

    return max(times, default=0.0)


def chain(name: str, animations: list[Animation], gap: float) -> tuple[Animation, list[float]]:
    chained = Animation(name)
    timelines: dict[str, Timeline] = {}
    starts = []
    offset = 0.0
    for animation in animations:
        starts.append(offset)
        for timeline in animation.timelines:
            target = timelines.setdefault(timeline.node, Timeline(timeline.node))
            for channel in ("translation", "rotation", "scale"):
                getattr(target, channel).extend((offset + time, values) for time, values in getattr(timeline, channel))
        offset += length(animation) + gap
    chained.timelines = list(timelines.values())
    for timeline in chained.timelines:
        timeline.rotation = _continuous(timeline.rotation)

    return chained, starts


def _continuous(keys: list[Key]) -> list[Key]:
    result = []
    for time, values in keys:
        if result and sum(a * b for a, b in zip(result[-1][1], values)) < 0:
            values = tuple(-v for v in values)
        result.append((time, values))

    return result
