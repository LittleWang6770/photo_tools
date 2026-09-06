#!/usr/bin/env python3
"""Copy GPS metadata from one template JPEG to a directory of JPEG photos."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


IMAGE_SUFFIXES = {".jpg", ".jpeg"}
BACKUP_DIRECTORY_NAME = ".batch-gps-copy-backup"
COORDINATE_TAGS = (
    "GPSLatitude",
    "GPSLongitude",
    "GPSLatitudeRef",
    "GPSLongitudeRef",
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass
class Summary:
    found: int = 0
    written: int = 0
    skipped_existing: int = 0
    failed: int = 0


def image_files(directory: Path, template: Path) -> Iterable[Path]:
    """Yield JPEG files recursively and deterministically."""
    template_resolved = template.resolve()
    for path in sorted(directory.rglob("*"), key=lambda item: str(item).casefold()):
        if BACKUP_DIRECTORY_NAME in path.parts:
            continue
        if (
            path.is_file()
            and path.suffix.lower() in IMAGE_SUFFIXES
            and path.resolve() != template_resolved
        ):
            yield path


def run_exiftool(executable: str, arguments: Sequence[str]) -> CommandResult:
    completed = subprocess.run(
        [executable, *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return CommandResult(
        completed.returncode,
        completed.stdout.strip(),
        completed.stderr.strip(),
    )


def read_gps(executable: str, path: Path) -> tuple[dict[str, object] | None, str]:
    result = run_exiftool(
        executable,
        ["-j", "-n", "-GPS:All", "-XMP-exif:GPS*", str(path)],
    )
    if result.returncode != 0:
        return None, result.stderr or result.stdout or "ExifTool 读取失败"
    try:
        records = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return None, f"无法解析 ExifTool 输出：{error}"
    return (records[0] if records else {}), result.stderr


def has_coordinates(metadata: dict[str, object]) -> bool:
    return all(metadata.get(tag) is not None for tag in COORDINATE_TAGS)


def has_gps(metadata: dict[str, object]) -> bool:
    """Treat any returned GPS tag as existing GPS metadata."""
    return any(key.startswith("GPS") and value is not None for key, value in metadata.items())


def copy_gps(executable: str, template: Path, target: Path) -> CommandResult:
    return run_exiftool(
        executable,
        [
            "-TagsFromFile",
            str(template),
            "-GPSLatitude",
            "-GPSLongitude",
            "-GPSLatitudeRef",
            "-GPSLongitudeRef",
            "-XMP-exif:GPSLatitude",
            "-XMP-exif:GPSLongitude",
            "-overwrite_original",
            str(target),
        ],
    )


def coordinate_values(metadata: dict[str, object]) -> tuple[float, float, str, str]:
    return (
        float(metadata["GPSLatitude"]),
        float(metadata["GPSLongitude"]),
        str(metadata["GPSLatitudeRef"]),
        str(metadata["GPSLongitudeRef"]),
    )


def verify_coordinates(
    executable: str,
    target: Path,
    expected: tuple[float, float, str, str],
) -> tuple[bool, str]:
    metadata, error = read_gps(executable, target)
    if metadata is None:
        return False, error
    if not has_coordinates(metadata):
        return False, "写入后仍缺少 GPS 经纬度"
    actual = coordinate_values(metadata)
    numbers_match = all(
        abs(left - right) < 1e-7
        for left, right in zip(expected[:2], actual[:2])
    )
    references_match = expected[2:] == actual[2:]
    if numbers_match and references_match:
        return True, ""
    return False, f"经纬度核验不一致：预期 {expected}，实际 {actual}"


def backup_path_for(photo: Path, directory: Path, backup_root: Path) -> Path:
    path = backup_root / photo.relative_to(directory)
    if not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return path.with_name(f"{path.stem}_{stamp}{path.suffix}")


def validate_paths(template: Path, directory: Path) -> None:
    if not template.is_file():
        raise FileNotFoundError(f"模板照片不存在或不是文件：{template}")
    if template.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("模板照片必须是 JPG/JPEG 文件。")
    if not directory.is_dir():
        raise NotADirectoryError(f"目标路径不存在或不是文件夹：{directory}")


def execute(args: argparse.Namespace) -> int:
    template = args.template_photo.expanduser().resolve()
    directory = args.directory.expanduser().resolve()
    validate_paths(template, directory)

    executable = shutil.which(args.exiftool)
    if executable is None:
        raise FileNotFoundError(
            f"找不到 ExifTool：{args.exiftool}。请按 README 安装，或用 --exiftool 指定路径。"
        )

    template_metadata, error = read_gps(executable, template)
    if template_metadata is None:
        raise ValueError(f"无法读取模板照片：{error}")
    if not has_coordinates(template_metadata):
        raise ValueError("模板照片没有完整的 GPS 经纬度。")

    photos = list(image_files(directory, template))
    summary = Summary(found=len(photos))
    if not photos:
        print("目标文件夹中没有可处理的 JPG/JPEG 照片。")
        return 0

    expected = coordinate_values(template_metadata)
    backup_root = directory / BACKUP_DIRECTORY_NAME
    print(
        f"找到 {len(photos)} 张照片，模板坐标："
        f"{expected[0]} {expected[2]}, {expected[1]} {expected[3]}"
    )

    for index, photo in enumerate(photos, start=1):
        relative = photo.relative_to(directory)
        print(f"[{index}/{len(photos)}] {relative}")
        metadata, error = read_gps(executable, photo)
        if metadata is None:
            summary.failed += 1
            print(f"  失败：{error}")
            continue
        if has_gps(metadata) and not args.force:
            summary.skipped_existing += 1
            print("  跳过：照片已有 GPS 信息（使用 -f 可强制覆盖）。")
            continue

        if not args.no_backup:
            destination = backup_path_for(photo, directory, backup_root)
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(photo, destination)
            except OSError as error:
                summary.failed += 1
                print(f"  失败：无法备份照片：{error}")
                continue

        result = copy_gps(executable, template, photo)
        if result.returncode != 0:
            summary.failed += 1
            print(f"  失败：{result.stderr or result.stdout or 'ExifTool 写入失败'}")
            continue

        verified, verify_error = verify_coordinates(executable, photo, expected)
        if not verified:
            summary.failed += 1
            print(f"  失败：{verify_error}")
            continue
        summary.written += 1
        print("  已写入并核验 GPS 经纬度。")

    print(
        f"处理完成：发现 {summary.found}，写入 {summary.written}，"
        f"已有 GPS 跳过 {summary.skipped_existing}，失败 {summary.failed}。"
    )
    return 1 if summary.failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="把一张模板照片的 GPS 经纬度批量复制到文件夹内的 JPG/JPEG。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("template_photo", type=Path, help="提供 GPS 信息的模板照片")
    parser.add_argument("directory", type=Path, help="需要批量写入 GPS 的照片文件夹")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="强制覆盖已有 GPS 信息；默认跳过",
    )
    parser.add_argument("--no-backup", action="store_true", help="不备份被修改的照片")
    parser.add_argument("--exiftool", default="exiftool", help="ExifTool 可执行文件名或路径")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return execute(args)
    except (FileNotFoundError, NotADirectoryError, ValueError, OSError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    sys.exit(main())
