"""Causal zero-order hold on an integer-nanosecond 15 Hz grid, within one episode."""

from bisect import bisect_right

OBSERVATIONS = ("rgb", "state")
COMMANDS = ("command", "left_command", "right_command")


def align(streams, timing):
    fps, offset = timing["fps"], timing["label_offset_ns"]
    if fps != 15 or type(offset) is not int:
        raise ValueError("expected 15Hz and signed integer offset")
    stamps = {}
    for name in (*OBSERVATIONS, *COMMANDS):
        values = [r["source_stamp_ns"] for r in streams[name]]
        if (not values or any(type(v) is not int or v < 0 for v in values)
                or any(b <= a for a, b in zip(values, values[1:]))):
            raise ValueError(f"empty/nonmonotonic stream: {name}")
        stamps[name] = values
    # label_time = observation_time + offset. Start/end are bounded by every stream.
    start = max(stamps[n][0] - (offset if n in COMMANDS else 0) for n in stamps)
    end = min(stamps[n][-1] - (offset if n in COMMANDS else 0) for n in stamps)
    frames = []
    index = 0
    while (sample := start + index * 1_000_000_000 // fps) <= end:
        chosen, times = {}, {}
        for name, values in stamps.items():
            target = sample + (offset if name in COMMANDS else 0)
            row = bisect_right(values, target) - 1
            if row < 0:
                raise ValueError(f"missing causal sample: {name}")
            chosen[name], times[name] = row, values[row]
            age = target - values[row]
            limit = timing["max_command_age_ns" if name in COMMANDS else "max_observation_age_ns"]
            if age > limit:
                raise ValueError(f"{name}: age {age} exceeds {limit} at frame {index}")
        for names, limit in ((OBSERVATIONS, timing["max_observation_skew_ns"]),
                             (COMMANDS, timing["max_command_skew_ns"])):
            if max(times[n] for n in names) - min(times[n] for n in names) > limit:
                raise ValueError(f"skew exceeds limit: {names} at frame {index}")
        frames.append({"frame_index": index, "observation_time_ns": sample,
                       "label_time_ns": sample + offset, "indices": chosen, "source_stamp_ns": times})
        index += 1
    if not frames:
        raise ValueError("no common sampling interval")
    return frames
