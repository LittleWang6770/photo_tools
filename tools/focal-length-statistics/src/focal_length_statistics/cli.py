#!/usr/bin/env python3
"""Report full-frame-equivalent focal-length frequency for JPEG photos."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .grouping import (
    DEFAULT_ANCHORS_TEXT,
    GROUPING_MODES,
    group_focal_length,
    parse_anchors,
    positive_decimal,
)


JPEG_SUFFIXES = {".jpg", ".jpeg"}
FOCAL_LENGTH_TAGS = ("FocalLengthIn35mmFormat", "FocalLength35efl")


@dataclass(frozen=True)
class FocalLengthRow:
    focal_length: Decimal
    count: int
    percentage: float


@dataclass(frozen=True)
class Statistics:
    scanned_images: int
    exif_images: int
    focal_length_images: int
    rows: tuple[FocalLengthRow, ...]


def iter_jpeg_files(input_path: Path) -> Iterable[Path]:
    """Yield JPG/JPEG files recursively without following file symlinks."""
    if input_path.is_file():
        if input_path.suffix.lower() in JPEG_SUFFIXES and not input_path.is_symlink():
            yield input_path
        return

    for path in sorted(input_path.rglob("*"), key=lambda item: str(item).casefold()):
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in JPEG_SUFFIXES:
            yield path


def exiftool_arguments(input_path: Path) -> list[str]:
    """Build a single recursive ExifTool query filtered to EXIF-bearing JPEGs."""
    arguments = ["-j", "-n", "-if", "$EXIF:all"]
    if input_path.is_dir():
        arguments.extend(["-r", "-ext", "jpg", "-ext", "jpeg"])
    arguments.extend(f"-{tag}" for tag in FOCAL_LENGTH_TAGS)
    arguments.append(str(input_path))
    return arguments


def read_exif_records(executable: str, input_path: Path) -> list[dict[str, object]]:
    completed = subprocess.run(
        [executable, *exiftool_arguments(input_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if not output and "files failed condition" in stderr:
        return []
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        detail = stderr or output or str(error)
        raise RuntimeError(f"ExifTool 读取失败：{detail}") from error
    if not isinstance(payload, list):
        raise RuntimeError("ExifTool JSON 输出格式异常：顶层数据不是列表。")
    return [record for record in payload if isinstance(record, dict)]


def extract_focal_length(record: Mapping[str, object]) -> Decimal | None:
    """Prefer the standard EXIF value and fall back to ExifTool's composite value."""
    for tag in FOCAL_LENGTH_TAGS:
        value = positive_decimal(record.get(tag))
        if value is not None:
            return value
    return None


def build_statistics(
    scanned_images: int,
    exif_records: Sequence[Mapping[str, object]],
    grouping_mode: str,
    anchors: Sequence[Decimal],
    bucket_size: Decimal,
) -> Statistics:
    frequencies: Counter[Decimal] = Counter()
    for record in exif_records:
        focal_length = extract_focal_length(record)
        if focal_length is not None:
            grouped_focal_length = group_focal_length(
                focal_length,
                grouping_mode,
                anchors,
                bucket_size,
            )
            frequencies[grouped_focal_length] += 1

    exif_images = len(exif_records)
    focal_length_images = sum(frequencies.values())
    sorted_frequencies = sorted(frequencies.items(), key=lambda item: (-item[1], item[0]))
    rows = tuple(
        FocalLengthRow(
            focal_length=focal_length,
            count=count,
            percentage=(count / exif_images * 100) if exif_images else 0.0,
        )
        for focal_length, count in sorted_frequencies
    )
    return Statistics(scanned_images, exif_images, focal_length_images, rows)


def visible_rows(
    rows: Sequence[FocalLengthRow],
    minimum_percentage: float,
    minimum_items: int,
) -> tuple[FocalLengthRow, ...]:
    """Show every qualifying row while guaranteeing at least the requested top N."""
    required_items = min(minimum_items, len(rows))
    return tuple(
        row
        for index, row in enumerate(rows)
        if index < required_items or row.percentage >= minimum_percentage
    )


def format_focal_length(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value, "f").rstrip("0").rstrip(".")


def print_report(
    statistics: Statistics,
    minimum_percentage: float,
    minimum_items: int,
    grouping_mode: str,
) -> None:
    print(f"共扫描 {statistics.scanned_images:,} 张 JPG/JPEG 图片。")
    print(f"共有 {statistics.exif_images:,} 张包含 EXIF 信息的图片。")
    if statistics.exif_images == 0:
        print("没有可统计的 EXIF 焦段信息。")
        return

    missing = statistics.exif_images - statistics.focal_length_images
    print(
        f"其中 {statistics.focal_length_images:,} 张包含可用的全画幅等效焦段，"
        f"{missing:,} 张缺少该字段。"
    )
    if not statistics.rows:
        print("没有可统计的全画幅等效焦段。")
        return

    displayed_rows = visible_rows(statistics.rows, minimum_percentage, minimum_items)
    report_name = (
        "标准焦段聚类统计"
        if grouping_mode == "standard"
        else "精确焦段统计"
    )
    print(f"\n{report_name}（按照片数量从高到低排序）：")
    for index, row in enumerate(displayed_rows, start=1):
        focal_length = format_focal_length(row.focal_length)
        print(
            f"{index:>2}. {focal_length} mm：{row.count:,} 张，"
            f"占含 EXIF 图片的 {row.percentage:.2f}%"
        )

    hidden_count = len(statistics.rows) - len(displayed_rows)
    if hidden_count:
        print(
            f"\n另有 {hidden_count} 个焦段因占比不足 {minimum_percentage:g}% 未显示；"
            f"已保证至少显示 Top {min(minimum_items, len(statistics.rows))}。"
        )


def validate_input(input_path: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"输入路径不存在：{input_path}")
    if not input_path.is_dir() and not input_path.is_file():
        raise ValueError(f"输入路径必须是目录或 JPG/JPEG 文件：{input_path}")
    if input_path.is_file() and input_path.suffix.lower() not in JPEG_SUFFIXES:
        raise ValueError(f"输入文件必须是 JPG/JPEG：{input_path}")


def execute(args: argparse.Namespace) -> int:
    input_path = args.input.expanduser().resolve()
    validate_input(input_path)
    jpeg_files = list(iter_jpeg_files(input_path))
    if not jpeg_files:
        print("输入路径下没有 JPG/JPEG 图片。")
        return 0

    executable = shutil.which(args.exiftool)
    if executable is None:
        raise FileNotFoundError(
            f"找不到 ExifTool：{args.exiftool}。请按 README 安装，"
            "或通过 --exiftool 指定路径。"
        )

    records = read_exif_records(executable, input_path)
    statistics = build_statistics(
        len(jpeg_files),
        records,
        args.grouping,
        args.anchors,
        args.bucket_size,
    )
    print_report(
        statistics,
        args.minimum_percentage,
        args.minimum_items,
        args.grouping,
    )
    return 0


def positive_decimal_argument(value: str) -> Decimal:
    decimal_value = positive_decimal(value)
    if decimal_value is None:
        raise argparse.ArgumentTypeError("必须是大于 0 的数字。")
    return decimal_value


def anchors_argument(value: str) -> tuple[Decimal, ...]:
    try:
        return parse_anchors(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def percentage_argument(value: str) -> float:
    try:
        percentage = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("必须是 0 到 100 之间的数字。") from error
    if not 0 <= percentage <= 100:
        raise argparse.ArgumentTypeError("必须是 0 到 100 之间的数字。")
    return percentage


def positive_integer_argument(value: str) -> int:
    try:
        integer = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数。") from error
    if integer < 1:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数。")
    return integer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="递归统计 JPG/JPEG 照片的全画幅等效焦段使用频度。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input",
        type=Path,
        help="需要递归扫描的图片目录或单张 JPG/JPEG",
    )
    parser.add_argument(
        "--grouping",
        choices=GROUPING_MODES,
        default="standard",
        help="standard 归入常用焦段；exact 保留精确焦段分组",
    )
    parser.add_argument(
        "--anchors",
        type=anchors_argument,
        default=DEFAULT_ANCHORS_TEXT,
        metavar="MM,...",
        help="standard 模式使用的标准焦段列表",
    )
    parser.add_argument(
        "--minimum-percentage",
        type=percentage_argument,
        default=5.0,
        help="隐藏低于该占比的焦段；Top N 不受此限制",
    )
    parser.add_argument(
        "--minimum-items",
        type=positive_integer_argument,
        default=5,
        help="无论占比多少，至少显示排名前 N 的焦段",
    )
    parser.add_argument(
        "--bucket-size",
        type=positive_decimal_argument,
        default=Decimal("1"),
        metavar="MM",
        help="exact 模式将焦段四舍五入到最接近的分组间隔",
    )
    parser.add_argument(
        "--exiftool",
        default="exiftool",
        help="ExifTool 可执行文件名或路径",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return execute(args)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    sys.exit(main())
