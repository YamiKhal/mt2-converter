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
