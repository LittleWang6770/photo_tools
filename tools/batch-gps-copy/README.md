# 批量复制照片 GPS

把一张 JPG/JPEG 模板照片中的 GPS 经纬度和南北/东西方向标记，递归复制到指定文件夹内的所有 JPG/JPEG 照片。海拔、GPS 时间等其他定位字段不会被复制。

- 目标照片已有任何 GPS 信息时默认跳过。
- 使用 `-f` 或 `--force` 强制覆盖已有 GPS。
- 写入后自动核验经纬度。
- 默认使用保守的并发数批量处理，并可通过 `-j/--workers` 调整。
- 终端使用单行进度条，不会为每张照片持续刷屏；进度条包含已用时间、预计总耗时和剩余时间，结束时显示实际总耗时。
- 修改前默认将原文件备份到目标文件夹内的 `.batch-gps-copy-backup/`；重复运行不会覆盖旧备份。
- 模板照片即使位于目标文件夹内也不会被处理。

## macOS App

现在可以直接双击 `dist/照片GPS复制.app`，通过 Finder 同款系统窗口选择 GPS 来源照片和待处理目录，无需安装 Python 或 ExifTool。

界面提供「跳过已有 GPS / 覆盖原图 GPS」、CPU 并发数、原图备份、进度与预计剩余时间，以及停止按钮。默认跳过已有 GPS，并在修改前备份原图。

当前成品适用于 Apple Silicon、macOS 26 或更新版本。详见 [App 使用与构建说明](macos/README.md)，[图标及绘图提示词](macos/assets/README.md)。

## 命令行安装

需要 Python 3.10+ 和 [ExifTool](https://exiftool.org/)。macOS 可执行：

```bash
brew install exiftool
cd tools/batch-gps-copy
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## 使用

默认跳过已有 GPS 的照片：

```bash
batch-gps-copy "/path/to/target_photo.JPG" "/path/to/photos"
```

强制覆盖已有 GPS：

```bash
batch-gps-copy -f "/path/to/target_photo.JPG" "/path/to/photos"
```

强制覆盖已有 GPS，并使用 4 个并发任务：

```bash
batch-gps-copy -f -j 4 "/path/to/target_photo.JPG" "/path/to/photos"
```

默认并发数会根据 CPU 核心数保守计算（8 核机器默认为 3）。需要进一步减少对其他应用的影响时可改为 1；机器空闲时也可手动增加：

```bash
batch-gps-copy -j 1 "/path/to/target_photo.JPG" "/path/to/photos"
batch-gps-copy -j 4 "/path/to/target_photo.JPG" "/path/to/photos"
```

允许的并发数范围是 1–32。对于 8 核、16 GB 的 MacBook Pro，日常使用建议保持默认值 3；更高数值会增加 CPU、内存和磁盘压力。

运行过程中，进度会在同一行更新：

```text
[███░░░░░░░]  33.3% 333/1000 | 已用 00:01:20 | 预计 00:04:00 | 剩余 00:02:40
```

其中“预计”表示预计总耗时。处理结束后会显示实际总耗时。普通使用命令不需要增加任何参数。

如明确不需要备份：

```bash
batch-gps-copy -f --no-backup target_photo.JPG /path/to/photos
```

工具只处理 `.jpg` 和 `.jpeg`（扩展名大小写不敏感），并递归处理子文件夹。模板照片必须包含完整的 GPS 纬度和经度，否则工具会拒绝运行。

## 测试

```bash
python3 -m unittest discover -s tests -v
```
