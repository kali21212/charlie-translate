"""OCR text layout helpers for Charlie Translate Desktop.

The layout heuristics are implemented in Python for Charlie's RapidOCR result shape.
They are inspired by the public smart-layout behavior documented/tested by
STranslate (MIT) and by Snow Shot's responsive OCR presentation, without
bringing either application's UI/runtime dependencies into Charlie.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from statistics import median
from typing import Iterable, Sequence


_LIST_RE = re.compile(r"^\s*(?:[-*+•·●▪]\s+|\d+[.)、]\s+)")
_SENTENCE_END = set(".!?;:。！？；：")


@dataclass(frozen=True)
class Bounds:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0

    @staticmethod
    def union(items: Iterable["Bounds"]) -> "Bounds":
        items = list(items)
        return Bounds(
            min(x.left for x in items),
            min(x.top for x in items),
            max(x.right for x in items),
            max(x.bottom for x in items),
        )


@dataclass
class LayoutItem:
    text: str
    bounds: Bounds


@dataclass
class Paragraph:
    lines: list[LayoutItem]

    @property
    def bounds(self) -> Bounds:
        return Bounds.union(line.bounds for line in self.lines)

    @property
    def last(self) -> LayoutItem:
        return self.lines[-1]


@dataclass
class Region:
    lines: list[LayoutItem]

    @property
    def bounds(self) -> Bounds:
        return Bounds.union(line.bounds for line in self.lines)


def _box_bounds(box) -> Bounds | None:
    try:
        points = list(box)
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    except (TypeError, ValueError, IndexError):
        return None
    if len(xs) < 2 or any(not math.isfinite(value) for value in xs + ys):
        return None
    value = Bounds(min(xs), min(ys), max(xs), max(ys))
    return value if value.width > 0 and value.height > 0 else None


def _overlap(first: Bounds, second: Bounds) -> float:
    width = max(0.0, min(first.right, second.right) - max(first.left, second.left))
    return width / max(1.0, min(first.width, second.width))


def _vertical_overlap(first: Bounds, second: Bounds) -> float:
    height = max(0.0, min(first.bottom, second.bottom) - max(first.top, second.top))
    return height / max(1.0, min(first.height, second.height))


def _vertical_gap(first: Bounds, second: Bounds) -> float:
    return max(0.0, second.top - first.bottom)


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x3040 <= code <= 0x30FF
        or 0xAC00 <= code <= 0xD7AF
    )


def _needs_space(previous: str, current: str) -> bool:
    if not previous or not current:
        return False
    left, right = previous[-1], current[0]
    if left.isspace() or right.isspace() or _is_cjk(left) or _is_cjk(right):
        return False
    if left in "([{“‘" or right in ".,!?;:)]}，。！？；：、”’":
        return False
    return True


def _hyphenated(previous: str, current: str) -> bool:
    return (
        len(previous) >= 2
        and bool(current)
        and previous.endswith("-")
        and previous[-2].isascii()
        and previous[-2].isalpha()
        and current[0].isascii()
        and current[0].islower()
    )


def _join_texts(texts: Sequence[str]) -> str:
    result = ""
    for raw in texts:
        value = " ".join(str(raw).strip().split())
        if not value:
            continue
        if not result:
            result = value
        elif _hyphenated(result, value):
            result = result[:-1] + value
        else:
            result += (" " if _needs_space(result, value) else "") + value
    return result


def _is_list_start(text: str) -> bool:
    return bool(_LIST_RE.match(text or ""))


def _ends_sentence(text: str) -> bool:
    for ch in reversed(text.rstrip()):
        if ch in '"\'’”)]}':
            continue
        return ch in _SENTENCE_END
    return False


def _starts_upper_latin(text: str) -> bool:
    for ch in text.lstrip():
        if ch in '"\'“‘([{':
            continue
        return "A" <= ch <= "Z"
    return False


def _looks_control(line: LayoutItem) -> bool:
    compact = line.text.replace(" ", "")
    if any(_is_cjk(ch) for ch in compact):
        return False
    return (
        not _is_list_start(line.text)
        and len(compact) <= 14
        and not any(ch.isspace() for ch in line.text)
        and line.bounds.width / max(line.bounds.height, 1.0) <= 6.2
        and not _ends_sentence(line.text)
    )


def _build_visual_lines(items: list[LayoutItem]) -> list[LayoutItem]:
    visual: list[list[LayoutItem]] = []
    for item in sorted(items, key=lambda x: (x.bounds.center_y, x.bounds.left)):
        target = None
        best = -1.0
        for group in visual:
            bounds = Bounds.union(x.bounds for x in group)
            overlap = _vertical_overlap(bounds, item.bounds)
            center_delta = abs(bounds.center_y - item.bounds.center_y)
            if overlap >= 0.55 or center_delta <= min(bounds.height, item.bounds.height) * 0.45:
                score = overlap - center_delta / max(bounds.height, item.bounds.height, 1.0) * 0.1
                if score > best:
                    best, target = score, group
        if target is None:
            visual.append([item])
        else:
            target.append(item)

    segments: list[LayoutItem] = []
    for group in visual:
        group = sorted(group, key=lambda x: x.bounds.left)
        heights = [x.bounds.height for x in group if x.bounds.height > 0]
        line_height = median(heights) if heights else 20.0
        current: list[LayoutItem] = []
        for item in group:
            if current:
                previous = current[-1]
                gap = item.bounds.left - previous.bounds.right
                inline = max(
                    line_height * 1.25,
                    min(line_height * 2.0, min(previous.bounds.width, item.bounds.width) * 0.75),
                )
                if gap > inline:
                    segments.append(
                        LayoutItem(_join_texts([x.text for x in current]), Bounds.union(x.bounds for x in current))
                    )
                    current = []
            current.append(item)
        if current:
            segments.append(
                LayoutItem(_join_texts([x.text for x in current]), Bounds.union(x.bounds for x in current))
            )
    return sorted(segments, key=lambda x: (x.bounds.top, x.bounds.left))


def _build_regions(lines: list[LayoutItem], line_height: float) -> list[Region]:
    regions: list[Region] = []
    for line in lines:
        best_region = None
        best_score = float("-inf")
        for region in regions:
            reference_score = float("-inf")
            for reference in region.lines[-4:]:
                if line.bounds.top < reference.bounds.top - line_height * 0.35:
                    continue
                gap = _vertical_gap(reference.bounds, line.bounds)
                if gap > line_height * 3.2:
                    continue
                overlap = _overlap(reference.bounds, line.bounds)
                left_delta = abs(reference.bounds.left - line.bounds.left)
                center_delta = abs(reference.bounds.center_x - line.bounds.center_x)
                affinity = (
                    overlap >= 0.30
                    or left_delta <= line_height * 1.8
                    or center_delta <= max(reference.bounds.width, line.bounds.width) * 0.35
                )
                if not affinity:
                    continue
                left_score = 1 - min(1, left_delta / max(line_height * 2, 1))
                center_score = 1 - min(
                    1, center_delta / max(max(reference.bounds.width, line.bounds.width), 1)
                )
                gap_score = 1 - min(1, gap / max(line_height * 3.2, 1))
                score = overlap * 4 + left_score * 2 + center_score + gap_score
                reference_score = max(reference_score, score)
            if reference_score > best_score:
                best_score, best_region = reference_score, region
        if best_region is None or best_score == float("-inf"):
            regions.append(Region([line]))
        else:
            best_region.lines.append(line)
    return regions


def _same_reading_band(first: Bounds, second: Bounds, line_height: float) -> bool:
    if _vertical_overlap(first, second) >= 0.25:
        return True
    top_delta = abs(first.top - second.top)
    return top_delta <= line_height * 2 and second.top <= first.bottom + line_height * 1.5


def _order_regions(regions: list[Region], line_height: float) -> list[Region]:
    pending = sorted(regions, key=lambda x: (x.bounds.top, x.bounds.left))
    ordered: list[Region] = []
    while pending:
        band = [pending.pop(0)]
        band_bounds = band[0].bounds
        index = 0
        while index < len(pending):
            candidate = pending[index]
            if _same_reading_band(band_bounds, candidate.bounds, line_height):
                band.append(candidate)
                band_bounds = Bounds.union([band_bounds, candidate.bounds])
                pending.pop(index)
            else:
                index += 1
        ordered.extend(sorted(band, key=lambda x: (x.bounds.left, x.bounds.top)))
    return ordered


def _normal_gap(lines: list[LayoutItem], line_height: float) -> float:
    gaps = [
        _vertical_gap(a.bounds, b.bounds)
        for a, b in zip(sorted(lines, key=lambda x: x.bounds.top), sorted(lines, key=lambda x: x.bounds.top)[1:])
    ]
    positive = [x for x in gaps if 0 <= x <= line_height * 1.5]
    return median(positive) if positive else line_height * 0.25


def _can_append(paragraph: Paragraph, current: LayoutItem, line_height: float, normal_gap: float) -> bool:
    previous = paragraph.last
    gap = _vertical_gap(previous.bounds, current.bounds)
    if gap > line_height * 1.25:
        return False
    if _is_list_start(current.text):
        return False
    if _is_list_start(previous.text) and current.bounds.left > previous.bounds.left + line_height * 0.8:
        return True
    min_height = max(1.0, min(previous.bounds.height, current.bounds.height))
    if max(previous.bounds.height, current.bounds.height) > min_height * 1.45:
        return False

    overlap = _overlap(previous.bounds, current.bounds)
    left_delta = abs(previous.bounds.left - current.bounds.left)
    if overlap < 0.45 and left_delta > line_height * 1.2:
        return False
    if _hyphenated(previous.text, current.text):
        return True
    if _looks_control(previous) or _looks_control(current):
        return False

    threshold = max(line_height * 0.72, min(normal_gap, line_height * 0.35) + line_height * 0.45)
    same_left = left_delta <= line_height * 0.8
    current_indented = current.bounds.left > previous.bounds.left + line_height * 0.8
    previous_short = previous.bounds.width <= current.bounds.width * 0.82
    if gap > threshold:
        if _ends_sentence(previous.text) and (same_left or current_indented):
            return False
        if _starts_upper_latin(current.text) and (same_left or current_indented):
            return False
        if previous_short and same_left:
            return False
    return True


def _paragraphs(region: Region, line_height: float) -> list[Paragraph]:
    lines = sorted(region.lines, key=lambda x: (x.bounds.top, x.bounds.left))
    normal_gap = _normal_gap(lines, line_height)
    paragraphs: list[Paragraph] = []
    for line in lines:
        candidates = [p for p in paragraphs if line.bounds.top >= p.last.bounds.top and _can_append(p, line, line_height, normal_gap)]
        if not candidates:
            paragraphs.append(Paragraph([line]))
            continue
        candidates.sort(
            key=lambda p: (
                _overlap(p.last.bounds, line.bounds) * 3
                - abs(p.last.bounds.left - line.bounds.left) / max(line_height, 1)
                - _vertical_gap(p.last.bounds, line.bounds) / max(line_height, 1)
            ),
            reverse=True,
        )
        candidates[0].lines.append(line)
    return sorted(paragraphs, key=lambda x: (x.bounds.top, x.bounds.left))


def reflow_plain_text(text: str) -> str:
    """Make OCR-style hard wraps readable without destroying explicit paragraphs."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text)
    output: list[str] = []
    for block in blocks:
        lines = [" ".join(line.strip().split()) for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        # Preserve obvious list items as separate logical lines; join wrapped continuations.
        current: list[str] = []
        for line in lines:
            if _is_list_start(line) and current:
                output.append(_join_texts(current))
                current = [line]
            else:
                current.append(line)
        if current:
            output.append(_join_texts(current))
    return "\n\n".join(value for value in output if value)


def format_ocr_result(result) -> str:
    """Return reading-order paragraphs from a RapidOCR-like result object."""
    raw_texts = getattr(result, "txts", None)
    raw_boxes = getattr(result, "boxes", None)
    raw_texts = list(raw_texts) if raw_texts is not None else []
    boxes = list(raw_boxes) if raw_boxes is not None else []
    texts = [str(x) for x in raw_texts if str(x).strip()]
    if not texts:
        return ""
    if len(boxes) != len(raw_texts):
        return reflow_plain_text("\n".join(texts))

    items: list[LayoutItem] = []
    for text, box in zip(raw_texts, boxes):
        value = str(text).strip()
        bounds = _box_bounds(box)
        if value and bounds is not None:
            items.append(LayoutItem(value, bounds))
    if len(items) < max(1, len(texts) // 2):
        return reflow_plain_text("\n".join(texts))

    lines = _build_visual_lines(items)
    heights = [line.bounds.height for line in lines if line.bounds.height > 0]
    line_height = median(heights) if heights else 20.0
    regions = _order_regions(_build_regions(lines, line_height), line_height)
    blocks: list[str] = []
    for region in regions:
        for paragraph in _paragraphs(region, line_height):
            value = _join_texts([line.text for line in paragraph.lines])
            if value:
                blocks.append(value)
    return "\n\n".join(blocks) if blocks else reflow_plain_text("\n".join(texts))
