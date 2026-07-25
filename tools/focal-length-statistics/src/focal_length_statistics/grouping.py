"""Group measured focal lengths into photographer-friendly focal-length buckets."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Sequence


DEFAULT_ANCHORS_TEXT = "14,16,20,24,28,35,40,50,70,85,105,135,200,300,400,600"
DEFAULT_ANCHORS = tuple(Decimal(value) for value in DEFAULT_ANCHORS_TEXT.split(","))
GROUPING_MODES = ("standard", "exact")


def positive_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return decimal_value if decimal_value.is_finite() and decimal_value > 0 else None


def parse_anchors(value: str) -> tuple[Decimal, ...]:
    """Parse, deduplicate, and sort a comma-separated focal-length list."""
    anchors = []
    for raw_value in value.split(","):
        anchor = positive_decimal(raw_value.strip())
        if anchor is None:
            raise ValueError("标准焦段必须是用英文逗号分隔的大于 0 的数字。")
        anchors.append(anchor.normalize())
    if not anchors:
        raise ValueError("至少需要一个标准焦段。")
    return tuple(sorted(set(anchors)))


def proportional_distance(value: Decimal, anchor: Decimal) -> Decimal:
    """Return a symmetric ratio distance; 50→100 and 100→50 are equally far."""
    return max(value / anchor, anchor / value)


def nearest_anchor(value: Decimal, anchors: Sequence[Decimal]) -> Decimal:
    """Choose the closest focal length by proportional rather than absolute distance."""
    if not anchors:
        raise ValueError("至少需要一个标准焦段。")
    return min(anchors, key=lambda anchor: (proportional_distance(value, anchor), anchor))


def normalize_exact_focal_length(value: Decimal, bucket_size: Decimal) -> Decimal:
    """Round exact-mode values to the nearest configurable interval."""
    bucket_index = (value / bucket_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return (bucket_index * bucket_size).normalize()


def group_focal_length(
    value: Decimal,
    mode: str,
    anchors: Sequence[Decimal],
    bucket_size: Decimal,
) -> Decimal:
    if mode == "standard":
        return nearest_anchor(value, anchors)
    if mode == "exact":
        return normalize_exact_focal_length(value, bucket_size)
    raise ValueError(f"未知焦段分组模式：{mode}")
