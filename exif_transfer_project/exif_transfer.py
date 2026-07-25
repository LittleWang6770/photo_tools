#!/usr/bin/env python3
"""Copy GPS or shooting metadata from original photos to exported JPEG files."""

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
BACKUP_DIRECTORY_NAME = ".exif-transfer-backup"
VERIFY_TAGS = (
    "GPSLatitude",
    "GPSLongitude",
    "GPSLatitudeRef",
    "GPSLongitudeRef",
    "GPSAltitude",
    "GPSAltitudeRef",
    "GPSDateStamp",
    "GPSTimeStamp",
)


@dataclass(frozen=True)
class PhotoPair:
    source: Path
    target: Path
    relative_target: Path


@dataclass
class Summary:
    matched: int = 0
    written: int = 0
    skipped_unchanged: int = 0
    skipped_no_gps: int = 0
    verify_failed: int = 0
    failed: int = 0


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def image_files(directory: Path, recursive: bool) -> Iterable[Path]:
    """Yield JPEG files deterministically, excluding this tool's backups."""
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    for path in sorted(iterator, key=lambda item: str(item).casefold()):
        if BACKUP_DIRECTORY_NAME in path.parts:
            continue
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            yield path


def relative_stem(path: Path, root: Path) -> str:
    return path.relative_to(root).with_suffix("").as_posix().casefold()


def discover_pairs(source: Path, target: Path, recursive: bool) -> tuple[list[PhotoPair], list[str]]:
    """Match files by extension-insensitive relative path and stem."""
    if source.is_file() and target.is_file():
        return [PhotoPair(source, target, Path(target.name))], []
    if not source.is_dir() or not target.is_dir():
        raise ValueError("源路径和目标路径必须同时为文件，或同时为目录。")

    source_index: dict[str, list[Path]] = {}
    for path in image_files(source, recursive):
        source_index.setdefault(relative_stem(path, source), []).append(path)

    pairs: list[PhotoPair] = []
    warnings: list[str] = []
    for target_file in image_files(target, recursive):
        key = relative_stem(target_file, target)
        candidates = source_index.get(key, [])
        if not candidates:
            warnings.append(f"找不到源图，跳过：{target_file.relative_to(target)}")
        elif len(candidates) > 1:
            names = ", ".join(str(item.relative_to(source)) for item in candidates)
            warnings.append(f"源图不唯一，跳过 {target_file.relative_to(target)}：{names}")
        else:
            pairs.append(PhotoPair(candidates[0], target_file, target_file.relative_to(target)))
    return pairs, warnings


def run_exiftool(executable: str, arguments: Sequence[str]) -> CommandResult:
    completed = subprocess.run(
        [executable, *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return CommandResult(completed.returncode, completed.stdout.strip(), completed.stderr.strip())


def read_gps(executable: str, path: Path) -> tuple[dict[str, object] | None, str]:
    arguments = ["-j", "-n", *(f"-{tag}" for tag in VERIFY_TAGS), str(path)]
    result = run_exiftool(executable, arguments)
    if result.returncode != 0:
        return None, result.stderr or result.stdout or "ExifTool 读取失败"
    try:
        records = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return None, f"无法解析 ExifTool 输出：{error}"
    return (records[0] if records else {}), result.stderr


def has_coordinates(metadata: dict[str, object]) -> bool:
    return metadata.get("GPSLatitude") is not None and metadata.get("GPSLongitude") is not None


def values_equal(source_value: object, target_value: object) -> bool:
    if source_value is None or target_value is None:
        return source_value is target_value
    if isinstance(source_value, (int, float)) and isinstance(target_value, (int, float)):
        return abs(float(source_value) - float(target_value)) < 1e-7
    return str(source_value).strip() == str(target_value).strip()


def gps_matches(source_metadata: dict[str, object], target_metadata: dict[str, object]) -> bool:
    """Return true when every GPS value present in the source already matches."""
    return all(
        source_metadata.get(tag) is None
        or values_equal(source_metadata.get(tag), target_metadata.get(tag))
        for tag in VERIFY_TAGS
    )


def verify_gps(
    executable: str,
    source_metadata: dict[str, object],
    target: Path,
) -> tuple[bool, list[str]]:
    target_metadata, error = read_gps(executable, target)
    if target_metadata is None:
        return False, [error]
    problems = []
    for tag in VERIFY_TAGS:
        source_value = source_metadata.get(tag)
        if source_value is not None and not values_equal(source_value, target_metadata.get(tag)):
            problems.append(
                f"{tag} 不一致：源={source_value!r}，目标={target_metadata.get(tag)!r}"
            )
    return not problems, problems


def copy_arguments(source: Path, target: Path, all_exif: bool, ignore_minor: bool = False) -> list[str]:
    arguments: list[str] = []
    if ignore_minor:
        arguments.append("-m")
    arguments.extend(["-TagsFromFile", str(source)])
    if all_exif:
        arguments.extend(
            [
                "-IFD0:All",
                "-ExifIFD:All",
                "-GPS:All",
                "-XMP-exif:All",
                "-XMP-exifEX:All",
                "-XMP-aux:All",
                "-x",
                "Orientation",
                "-x",
                "ImageWidth",
                "-x",
                "ImageHeight",
                "-x",
                "ExifImageWidth",
                "-x",
                "ExifImageHeight",
                "-x",
                "ThumbnailImage",
            ]
        )
    else:
        arguments.extend(["-GPS:All", "-XMP-exif:GPS*"])
    arguments.extend(["-overwrite_original", str(target)])
    return arguments


def unique_backup_path(path: Path) -> Path:
    if not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return path.with_name(f"{path.stem}_{stamp}{path.suffix}")


def create_backup(pair: PhotoPair, backup_root: Path) -> Path:
    backup_path = unique_backup_path(backup_root / pair.relative_target)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pair.target, backup_path)
    return backup_path


def copy_with_optional_repair(
    executable: str,
    pair: PhotoPair,
    all_exif: bool,
    repair_broken_exif: bool,
) -> tuple[bool, str, CommandResult]:
    result = run_exiftool(executable, copy_arguments(pair.source, pair.target, all_exif))
    if result.returncode == 0:
        return True, "normal", result
    if "Bad IFD" not in result.stderr:
        return False, "failed", result

    retry = run_exiftool(
        executable,
        copy_arguments(pair.source, pair.target, all_exif, ignore_minor=True),
    )
    if retry.returncode == 0:
        return True, "ignore_minor", retry
    if not repair_broken_exif:
        return False, "failed", retry

    clear_result = run_exiftool(
        executable,
        ["-m", "-EXIF:All=", "-overwrite_original", str(pair.target)],
    )
    if clear_result.returncode != 0:
        return False, "failed", clear_result
    rebuilt = run_exiftool(
        executable,
        copy_arguments(pair.source, pair.target, all_exif, ignore_minor=True),
    )
    return rebuilt.returncode == 0, "rebuild_exif" if rebuilt.returncode == 0 else "failed", rebuilt


def validate_paths(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"源路径不存在：{source}")
    if not target.exists():
        raise FileNotFoundError(f"目标路径不存在：{target}")
    if source.resolve() == target.resolve():
        raise ValueError("源路径和目标路径不能相同。")
    if source.is_file() and source.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("源文件必须是 JPG/JPEG。")
    if target.is_file() and target.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("目标文件必须是 JPG/JPEG。")


def default_backup_root(target: Path) -> Path:
    parent = target if target.is_dir() else target.parent
    return parent / BACKUP_DIRECTORY_NAME


def execute(args: argparse.Namespace) -> int:
    source = args.source.expanduser().resolve()
    target = args.target.expanduser().resolve()
    validate_paths(source, target)
    pairs, warnings = discover_pairs(source, target, args.recursive)

    for warning in warnings:
        print(f"警告：{warning}")
    if not pairs:
        print("没有找到可匹配的 JPG/JPEG 文件。")
        return 0

    print(f"找到 {len(pairs)} 对照片。")
    if args.dry_run:
        for pair in pairs:
            print(f"[预览] {pair.source} -> {pair.target}")
        print("预览完成，未修改文件。")
        return 0

    executable = shutil.which(args.exiftool)
    if executable is None:
        raise FileNotFoundError(
            f"找不到 ExifTool：{args.exiftool}。请按 README 安装，或通过 --exiftool 指定路径。"
        )
    backup_root = (
        args.backup_dir.expanduser().resolve() if args.backup_dir else default_backup_root(target)
    )
    summary = Summary(matched=len(pairs))

    for index, pair in enumerate(pairs, start=1):
        print(f"[{index}/{len(pairs)}] {pair.relative_target}")
        source_metadata, read_error = read_gps(executable, pair.source)
        if source_metadata is None:
            summary.failed += 1
            print(f"  失败：{read_error}")
            continue
        if not has_coordinates(source_metadata):
            summary.skipped_no_gps += 1
            print("  跳过：源图没有完整的 GPS 经纬度。")
            continue

        if not args.all_exif:
            target_metadata, _ = read_gps(executable, pair.target)
            if target_metadata is not None and gps_matches(source_metadata, target_metadata):
                summary.skipped_unchanged += 1
                print("  跳过：目标图的 GPS 已一致。")
                continue

        if not args.no_backup:
            try:
                backup_path = create_backup(pair, backup_root)
                print(f"  备份：{backup_path}")
            except OSError as error:
                summary.failed += 1
                print(f"  失败：无法备份目标文件：{error}")
                continue

        success, mode, result = copy_with_optional_repair(
            executable,
            pair,
            args.all_exif,
            args.repair_broken_exif,
        )
        if not success:
            summary.failed += 1
            print(f"  失败：{result.stderr or result.stdout or 'ExifTool 写入失败'}")
            continue

        summary.written += 1
        print(f"  已写入（{mode}）。")
        if not args.no_verify:
            verified, problems = verify_gps(executable, source_metadata, pair.target)
            if not verified:
                summary.verify_failed += 1
                print("  核验失败：" + "; ".join(problems))

    print("\n处理完成")
    print(
        f"匹配：{summary.matched}，写入：{summary.written}，"
        f"已一致跳过：{summary.skipped_unchanged}，无 GPS 跳过：{summary.skipped_no_gps}"
    )
    print(f"核验失败：{summary.verify_failed}，处理失败：{summary.failed}")
    return 1 if summary.failed or summary.verify_failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="把原图的 GPS 经纬度迁移到同名导出图。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("source", type=Path, help="包含原图的文件或目录")
    parser.add_argument("target", type=Path, help="需要写入元数据的文件或目录")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归匹配相同相对路径和文件名")
    parser.add_argument("--all-exif", action="store_true", help="迁移拍摄 EXIF/XMP，而不仅是 GPS")
    parser.add_argument("--dry-run", action="store_true", help="只显示匹配结果，不读取或修改元数据")
    parser.add_argument("--backup-dir", type=Path, help="自定义目标图备份目录")
    parser.add_argument("--no-backup", action="store_true", help="不备份目标图（不推荐）")
    parser.add_argument("--no-verify", action="store_true", help="写入后不核验 GPS")
    parser.add_argument(
        "--repair-broken-exif",
        action="store_true",
        help="遇到 Bad IFD 且重试失败时，清除目标 EXIF 后重建",
    )
    parser.add_argument("--exiftool", default="exiftool", help="ExifTool 可执行文件名或路径")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.no_backup and args.backup_dir:
        parser.error("--no-backup 和 --backup-dir 不能同时使用。")
    try:
        return execute(args)
    except (FileNotFoundError, NotADirectoryError, ValueError, OSError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    sys.exit(main())
