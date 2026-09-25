"""Parse GitHub unified hunks, failing closed on incomplete patches."""
import re
from dataclasses import dataclass, field


class DiffParseError(ValueError):
    pass


@dataclass
class DiffLines:
    added_lines: set[int] = field(default_factory=set)
    new_lines: set[int] = field(default_factory=set)
    removed_lines: set[int] = field(default_factory=set)


def parse_diff(patch: str) -> DiffLines:
    result = DiffLines()
    old_left = new_left = 0
    old = new = 0
    previous_old = previous_new = 0
    seen = False
    for text in patch.splitlines():
        if text.startswith("@@"):
            if old_left or new_left:
                raise DiffParseError("incomplete_diff_hunk")
            match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*", text)
            if not match:
                raise DiffParseError("invalid_diff_hunk")
            old, new = int(match[1]), int(match[3])
            old_left = int(match[2]) if match[2] is not None else 1
            new_left = int(match[4]) if match[4] is not None else 1
            if (old_left and old < 1) or (new_left and new < 1):
                raise DiffParseError("invalid_diff_position")
            if seen and (old < previous_old or new < previous_new):
                raise DiffParseError("overlapping_diff_hunks")
            previous_old, previous_new = old + old_left, new + new_left
            seen = True
        elif seen and text == chr(92) + " No newline at end of file":
            continue
        elif seen and text.startswith("+"):
            result.added_lines.add(new)
            result.new_lines.add(new)
            new += 1
            new_left -= 1
        elif seen and text.startswith("-"):
            result.removed_lines.add(old)
            old += 1
            old_left -= 1
        elif seen and text.startswith(" "):
            result.new_lines.add(new)
            old += 1
            new += 1
            old_left -= 1
            new_left -= 1
        else:
            raise DiffParseError("invalid_diff_body")
        if old_left < 0 or new_left < 0:
            raise DiffParseError("invalid_diff_counts")
    if not seen or old_left or new_left:
        raise DiffParseError("incomplete_diff_hunk")
    return result
