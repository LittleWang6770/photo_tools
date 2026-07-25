#!/usr/bin/env python3
"""Safely compress JPEG and PNG images in batches."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import multiprocessing
import os
import shutil
import stat
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence, TextIO

from PIL import Image, PngImagePlugin, UnidentifiedImageError


FORMAT_BY_EXTENSION = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}
PROFILE_WORKERS = {"balanced": 4, "light": 2, "hdd": 1}
STATE_FILE_NAME = ".photo-compress-state.jsonl"
LOG_FILE_NAME = "photo-compress-log.csv"


@dataclass(frozen=True)
class CompressTask:
    source_path: str
    destination_path: str
    relative_path: str
    image_format: str
    in_place: bool
    quality: int
    optimize: bool
    progressive: bool
    png_compress_level: int
    verify: bool
    settings_signature: str


@dataclass
class CompressResult:
    relative_path: str
    image_format: str
    status: str
    original_size: int
    output_size: int
    output_mtime_ns: int
    elapsed_seconds: float
    settings_signature: str
    error: str = ""


@dataclass
class ScanSummary:
    found: int = 0
    queued: int = 0
    skipped_existing: int = 0
    skipped_state: int = 0
    skipped_format: int = 0
    input_bytes: int = 0


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def initialize_worker(nice_increment: int) -> None:
    if nice_increment <= 0:
        return
    try:
        os.nice(nice_increment)
    except OSError:
        pass


def iter_images(root: Path, recursive: bool) -> Iterator[Path]:
    iterator: Iterable[Path] = root.rglob("*") if recursive else root.iterdir()
    for path in sorted(iterator, key=lambda item: str(item).casefold()):
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in FORMAT_BY_EXTENSION:
            yield path


def selected_format(image_format: str, requested_format: str) -> bool:
    return requested_format == "all" or requested_format.upper() == image_format


def make_settings_signature(
    image_format: str,
    quality: int,
    optimize: bool,
    progressive: bool,
    png_compress_level: int,
) -> str:
    settings = {
        "version": 1,
        "format": image_format,
        "quality": quality if image_format == "JPEG" else None,
        "optimize": optimize,
        "progressive": progressive if image_format == "JPEG" else None,
        "png_compress_level": png_compress_level if image_format == "PNG" else None,
    }
    encoded = json.dumps(settings, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def load_state(path: Path) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return state
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                relative_path = record.get("relative_path")
                if isinstance(relative_path, str):
                    state[relative_path] = record
    except OSError as error:
        print(f"警告：无法读取断点文件 {path}：{error}")
    return state


def already_processed(
    path: Path,
    relative_path: str,
    signature: str,
    state: dict[str, dict[str, Any]],
) -> bool:
    record = state.get(relative_path)
    if record is None:
        return False
    try:
        current = path.stat()
    except OSError:
        return False
    return (
        record.get("output_size") == current.st_size
        and record.get("output_mtime_ns") == current.st_mtime_ns
        and record.get("settings_signature") == signature
    )


def append_state(handle: TextIO, result: CompressResult) -> None:
    record = {
        "relative_path": result.relative_path,
        "image_format": result.image_format,
        "settings_signature": result.settings_signature,
        "output_size": result.output_size,
        "output_mtime_ns": result.output_mtime_ns,
        "status": result.status,
        "processed_at": time.time(),
    }
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()


def build_tasks(
    input_directory: Path,
    output_directory: Path | None,
    args: argparse.Namespace,
    state: dict[str, dict[str, Any]],
) -> tuple[list[CompressTask], ScanSummary]:
    tasks: list[CompressTask] = []
    summary = ScanSummary()
    for source in iter_images(input_directory, args.recursive):
        summary.found += 1
        image_format = FORMAT_BY_EXTENSION[source.suffix.lower()]
        if not selected_format(image_format, args.format):
            summary.skipped_format += 1
            continue
        relative = source.relative_to(input_directory)
        relative_string = relative.as_posix()
        destination = source if args.in_place else output_directory / relative  # type: ignore[operator]
        signature = make_settings_signature(
            image_format,
            args.quality,
            args.optimize,
            args.progressive,
            args.png_compress_level,
        )

        if args.in_place and not args.force and already_processed(
            source, relative_string, signature, state
        ):
            summary.skipped_state += 1
            continue
        if not args.in_place and destination.exists() and not args.overwrite:
            summary.skipped_existing += 1
            continue

        try:
            summary.input_bytes += source.stat().st_size
        except OSError:
            pass
        tasks.append(
            CompressTask(
                source_path=str(source),
                destination_path=str(destination),
                relative_path=relative_string,
                image_format=image_format,
                in_place=args.in_place,
                quality=args.quality,
                optimize=args.optimize,
                progressive=args.progressive,
                png_compress_level=args.png_compress_level,
                verify=args.verify,
                settings_signature=signature,
            )
        )
        if args.limit is not None and len(tasks) >= args.limit:
            break
    summary.queued = len(tasks)
    return tasks, summary


def read_extended_attributes(path: Path) -> dict[str, bytes]:
    attributes: dict[str, bytes] = {}
    if not hasattr(os, "listxattr"):
        return attributes
    try:
        for name in os.listxattr(path):
            try:
                attributes[name] = os.getxattr(path, name)
            except OSError:
                continue
    except OSError:
        pass
    return attributes


def write_extended_attributes(path: Path, attributes: dict[str, bytes]) -> None:
    if not hasattr(os, "setxattr"):
        return
    for name, value in attributes.items():
        try:
            os.setxattr(path, name, value)
        except OSError:
            continue


def restore_file_metadata(path: Path, original: os.stat_result) -> None:
    try:
        os.chmod(path, stat.S_IMODE(original.st_mode))
    except OSError:
        pass
    try:
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    except OSError:
        pass


def save_jpeg(image: Image.Image, path: Path, task: CompressTask) -> None:
    image.load()
    info = image.info
    if image.mode not in ("RGB", "L", "CMYK"):
        image = image.convert("RGB")
    options: dict[str, Any] = {
        "format": "JPEG",
        "quality": task.quality,
        "optimize": task.optimize,
        "progressive": task.progressive,
    }
    for key in ("exif", "icc_profile", "dpi", "comment"):
        if info.get(key):
            options[key] = info[key]
    try:
        image.save(path, **options)
    except OSError:
        if not task.optimize:
            raise
        path.unlink(missing_ok=True)
        options["optimize"] = False
        image.save(path, **options)


def png_text_info(image: Image.Image) -> PngImagePlugin.PngInfo | None:
    text_values = getattr(image, "text", {})
    if not isinstance(text_values, dict):
        return None
    result = PngImagePlugin.PngInfo()
    count = 0
    for key, value in text_values.items():
        if isinstance(key, str) and isinstance(value, str):
            try:
                result.add_text(key, value)
                count += 1
            except (UnicodeError, ValueError):
                pass
    return result if count else None


def save_png(image: Image.Image, path: Path, task: CompressTask) -> None:
    image.load()
    options: dict[str, Any] = {
        "format": "PNG",
        "optimize": task.optimize,
        "compress_level": task.png_compress_level,
    }
    text_info = png_text_info(image)
    if text_info is not None:
        options["pnginfo"] = text_info
    for key in ("icc_profile", "exif", "dpi"):
        if image.info.get(key) is not None:
            options[key] = image.info[key]
    if image.info.get("transparency") is not None and image.mode in {"P", "1", "L", "I", "RGB"}:
        options["transparency"] = image.info["transparency"]
    if image.info.get("bits") is not None and image.mode == "P":
        options["bits"] = image.info["bits"]
    image.save(path, **options)


def verify_image(path: Path, expected_format: str, expected_size: tuple[int, int]) -> None:
    with Image.open(path) as image:
        if image.format != expected_format:
            raise ValueError(f"输出格式异常：期望 {expected_format}，实际 {image.format}")
        if image.size != expected_size:
            raise ValueError(f"输出尺寸异常：期望 {expected_size}，实际 {image.size}")
        image.verify()


def result_for(
    task: CompressTask,
    status: str,
    original_size: int,
    output_size: int,
    output_mtime_ns: int,
    started_at: float,
    error: str = "",
) -> CompressResult:
    return CompressResult(
        relative_path=task.relative_path,
        image_format=task.image_format,
        status=status,
        original_size=original_size,
        output_size=output_size,
        output_mtime_ns=output_mtime_ns,
        elapsed_seconds=time.perf_counter() - started_at,
        settings_signature=task.settings_signature,
        error=error,
    )


def compress_one(task: CompressTask) -> CompressResult:
    started_at = time.perf_counter()
    source = Path(task.source_path)
    destination = Path(task.destination_path)
    temporary: Path | None = None
    try:
        original_stat = source.stat()
        original_size = original_stat.st_size
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix=f".{destination.stem}_compress_", suffix=".tmp", dir=destination.parent
        )
        os.close(descriptor)
        temporary = Path(name)
        attributes = read_extended_attributes(source)

        with Image.open(source) as image:
            original_dimensions = image.size
            if task.image_format == "PNG" and (
                bool(getattr(image, "is_animated", False)) or int(getattr(image, "n_frames", 1)) > 1
            ):
                temporary.unlink(missing_ok=True)
                current = source.stat()
                return result_for(
                    task, "skipped_animated", original_size, current.st_size, current.st_mtime_ns, started_at
                )
            if task.image_format == "JPEG":
                save_jpeg(image, temporary, task)
            else:
                save_png(image, temporary, task)

        if task.verify:
            verify_image(temporary, task.image_format, original_dimensions)
        compressed_size = temporary.stat().st_size

        if compressed_size >= original_size:
            temporary.unlink(missing_ok=True)
            temporary = None
            if task.in_place:
                current = source.stat()
                return result_for(
                    task, "kept_original", original_size, current.st_size, current.st_mtime_ns, started_at
                )
            descriptor, name = tempfile.mkstemp(
                prefix=f".{destination.stem}_copy_", suffix=".tmp", dir=destination.parent
            )
            os.close(descriptor)
            temporary = Path(name)
            shutil.copy2(source, temporary)
            status = "copied_original"
        else:
            status = "compressed"
            write_extended_attributes(temporary, attributes)

        os.replace(temporary, destination)
        temporary = None
        restore_file_metadata(destination, original_stat)
        write_extended_attributes(destination, attributes)
        output_stat = destination.stat()
        return result_for(
            task,
            status,
            original_size,
            output_stat.st_size,
            output_stat.st_mtime_ns,
            started_at,
        )
    except (UnidentifiedImageError, OSError, ValueError) as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        try:
            current = destination.stat() if destination.exists() else source.stat()
            size, mtime = current.st_size, current.st_mtime_ns
        except OSError:
            size, mtime = 0, 0
        return result_for(task, "failed", locals().get("original_size", 0), size, mtime, started_at, str(error))
    except Exception as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        return result_for(
            task,
            "failed",
            locals().get("original_size", 0),
            0,
            0,
            started_at,
            f"未知错误：{error}",
        )


def path_is_inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_arguments(args: argparse.Namespace) -> tuple[Path, Path | None]:
    input_directory = args.input.expanduser().resolve()
    if not input_directory.exists():
        raise FileNotFoundError(f"输入目录不存在：{input_directory}")
    if not input_directory.is_dir():
        raise NotADirectoryError(f"输入路径不是目录：{input_directory}")
    if input_directory == Path(input_directory.anchor):
        raise ValueError("出于安全考虑，不允许处理文件系统根目录。")
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit 必须大于 0。")
    if args.workers is not None and args.workers < 1:
        raise ValueError("--workers 必须大于 0。")
    if args.nice < 0:
        raise ValueError("--nice 不能小于 0。")
    if args.in_place and args.overwrite:
        raise ValueError("--overwrite 只适用于 --output 模式。")

    output_directory = None
    if args.output is not None:
        output_directory = args.output.expanduser().resolve()
        if output_directory == Path(output_directory.anchor):
            raise ValueError("出于安全考虑，不允许把文件系统根目录作为输出目录。")
        if output_directory == input_directory:
            raise ValueError("输出目录不能等于输入目录；原地压缩请使用 --in-place。")
        if path_is_inside(output_directory, input_directory):
            raise ValueError("输出目录不能位于输入目录内部，以免递归处理输出文件。")
    return input_directory, output_directory


def default_runtime_path(input_directory: Path, output_directory: Path | None, name: str) -> Path:
    root = output_directory if output_directory is not None else input_directory
    return root / name


def print_scan_summary(summary: ScanSummary, args: argparse.Namespace, workers: int) -> None:
    mode = "原地压缩" if args.in_place else "输出到新目录"
    print("=" * 64)
    print(f"模式：{mode}")
    print(f"发现图片：{summary.found}，待处理：{summary.queued}")
    print(f"已有输出跳过：{summary.skipped_existing}，断点跳过：{summary.skipped_state}")
    print(f"格式过滤跳过：{summary.skipped_format}")
    print(f"待处理大小：{format_size(summary.input_bytes)}，工作进程：{workers}")
    print("=" * 64)


def process_results(
    tasks: list[CompressTask],
    workers: int,
    nice_increment: int,
) -> Iterator[CompressResult]:
    if workers == 1:
        initialize_worker(nice_increment)
        for task in tasks:
            yield compress_one(task)
        return
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=context,
        initializer=initialize_worker,
        initargs=(nice_increment,),
    ) as executor:
        yield from executor.map(compress_one, tasks, chunksize=1)


def execute(args: argparse.Namespace) -> int:
    input_directory, output_directory = validate_arguments(args)
    workers = args.workers or PROFILE_WORKERS[args.profile]
    state_path = (
        args.state_file.expanduser().resolve()
        if args.state_file
        else default_runtime_path(input_directory, output_directory, STATE_FILE_NAME)
    )
    state = load_state(state_path) if args.in_place and not args.force else {}
    tasks, scan_summary = build_tasks(input_directory, output_directory, args, state)
    print_scan_summary(scan_summary, args, workers)
    if args.dry_run:
        for task in tasks[:20]:
            print(f"[预览] {task.relative_path}")
        if len(tasks) > 20:
            print(f"……另有 {len(tasks) - 20} 张")
        print("预览完成，未创建或修改文件。")
        return 0
    if not tasks:
        print("没有需要处理的图片。")
        return 0

    if output_directory is not None:
        output_directory.mkdir(parents=True, exist_ok=True)
    log_path = (
        args.log_file.expanduser().resolve()
        if args.log_file
        else default_runtime_path(input_directory, output_directory, LOG_FILE_NAME)
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    state_handle: TextIO | None = None
    if args.in_place:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_handle = state_path.open("a", encoding="utf-8")

    counts = {"compressed": 0, "copied_original": 0, "kept_original": 0, "skipped_animated": 0, "failed": 0}
    original_bytes = 0
    output_bytes = 0
    started_at = time.perf_counter()
    try:
        with log_path.open("w", newline="", encoding="utf-8-sig") as log_handle:
            writer = csv.DictWriter(log_handle, fieldnames=[*asdict(CompressResult("", "", "", 0, 0, 0, 0.0, "")).keys()])
            writer.writeheader()
            for index, result in enumerate(process_results(tasks, workers, args.nice), start=1):
                counts[result.status] += 1
                original_bytes += result.original_size
                output_bytes += result.output_size
                writer.writerow(asdict(result))
                if state_handle is not None and result.status != "failed":
                    append_state(state_handle, result)
                if result.error:
                    print(f"[{index}/{len(tasks)}] 失败 {result.relative_path}：{result.error}")
                elif index % args.progress_interval == 0 or index == len(tasks):
                    print(
                        f"[{index}/{len(tasks)}] 压缩 {counts['compressed']}，"
                        f"保留/复制原图 {counts['kept_original'] + counts['copied_original']}，"
                        f"动画跳过 {counts['skipped_animated']}，失败 {counts['failed']}"
                    )
                log_handle.flush()
    finally:
        if state_handle is not None:
            state_handle.close()

    elapsed = time.perf_counter() - started_at
    saving = (1 - output_bytes / original_bytes) * 100 if original_bytes else 0.0
    print("\n处理完成")
    print(f"处理前：{format_size(original_bytes)}，处理后：{format_size(output_bytes)}，节省：{saving:.2f}%")
    print(f"耗时：{elapsed:.2f} 秒，日志：{log_path}")
    return 1 if counts["failed"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量压缩 JPEG/PNG；推荐输出到新目录，原地模式需显式启用。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="输入图片目录")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("-o", "--output", type=Path, help="压缩结果目录")
    mode.add_argument("--in-place", action="store_true", help="原地替换体积变小的图片（请先备份）")
    parser.add_argument("--format", choices=("all", "jpeg", "png"), default="all", help="处理的图片格式")
    parser.add_argument("--quality", type=int, choices=range(1, 96), default=88, metavar="1-95", help="JPEG 质量")
    parser.add_argument("--png-compress-level", type=int, choices=range(10), default=9, metavar="0-9", help="PNG 无损压缩等级")
    parser.add_argument("--profile", choices=tuple(PROFILE_WORKERS), default="balanced", help="并发预设")
    parser.add_argument("--workers", type=int, help="覆盖预设进程数")
    parser.add_argument("--nice", type=int, default=10, help="降低工作进程优先级的 nice 增量")
    parser.add_argument("--limit", type=int, help="最多处理多少张，用于小批量试跑")
    parser.add_argument("--overwrite", action="store_true", help="覆盖输出目录中已有文件")
    parser.add_argument("--force", action="store_true", help="原地模式忽略断点记录并重新压缩")
    parser.add_argument("--dry-run", action="store_true", help="仅扫描并预览，不写文件")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false", help="仅处理输入目录第一层")
    parser.add_argument("--no-optimize", dest="optimize", action="store_false", help="关闭额外编码优化")
    parser.add_argument("--no-progressive", dest="progressive", action="store_false", help="关闭渐进式 JPEG")
    parser.add_argument("--no-verify", dest="verify", action="store_false", help="不重新打开临时图片进行校验")
    parser.add_argument("--state-file", type=Path, help="自定义原地模式断点文件")
    parser.add_argument("--log-file", type=Path, help="自定义 CSV 日志")
    parser.add_argument("--progress-interval", type=int, default=100, help="每多少张显示一次进度")
    parser.set_defaults(recursive=True, optimize=True, progressive=True, verify=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.progress_interval < 1:
        parser.error("--progress-interval 必须大于 0。")
    if args.force and not args.in_place:
        parser.error("--force 只适用于 --in-place。")
    if args.state_file and not args.in_place:
        parser.error("--state-file 只适用于 --in-place。")
    try:
        return execute(args)
    except (FileNotFoundError, NotADirectoryError, ValueError, OSError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
