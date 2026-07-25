# 照片经纬度迁移工具

把原始 JPG/JPEG 中的 GPS 经纬度复制到同名的导出照片。默认只迁移 GPS，并在修改前备份目标图；也可以选择迁移相机、镜头和拍摄时间等 EXIF/XMP 信息。

适合这样的工作流：原图包含定位信息，但 Photoshop、Lightroom 或其他导出流程生成的照片丢失了定位信息。

## 特性

- 支持单文件和批量目录。
- 目录模式按“不含扩展名的相对路径”匹配，扩展名和大小写不敏感。
- 默认只复制 GPS，不改变目标图方向、尺寸或像素。
- 默认把修改前的目标图保存到 `.exif-transfer-backup/`。
- 重复运行时跳过 GPS 已一致的目标图，不产生多余备份。
- 写入后对经纬度等关键 GPS 字段进行数值核验。
- 可选迁移完整拍摄 EXIF，可选修复目标图中的 `Bad IFD`。
- `--dry-run` 可先预览匹配结果。

## 环境要求

- Python 3.10 或更新版本。
- [ExifTool](https://exiftool.org/) 命令行程序。

macOS 使用 Homebrew 安装：

```bash
brew install exiftool
```

Ubuntu/Debian：

```bash
sudo apt install libimage-exiftool-perl
```

创建独立环境并安装工具：

```bash
cd tools/gps-metadata-transfer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
gps-metadata-transfer --help
```

Python 部分只使用标准库；`pip install -e .` 用于注册命令行入口，方便开发和更新。也可以使用 `python -m gps_metadata_transfer` 运行同一入口。

## 快速开始

先预览将要匹配的照片：

```bash
gps-metadata-transfer "/path/to/originals" "/path/to/exports" --dry-run
```

确认匹配正确后迁移 GPS：

```bash
gps-metadata-transfer "/path/to/originals" "/path/to/exports"
```

递归处理子目录：

```bash
gps-metadata-transfer "/path/to/originals" "/path/to/exports" --recursive
```

处理单张照片：

```bash
gps-metadata-transfer source.JPG target.jpeg
```

默认备份目录位于目标目录下：

```text
exports/
├── photo-001.jpg
└── .exif-transfer-backup/
    └── photo-001.jpg
```

## 常用选项

迁移相机、镜头、拍摄时间以及 GPS 等拍摄元数据：

```bash
gps-metadata-transfer originals exports --all-exif
```

指定备份位置：

```bash
gps-metadata-transfer originals exports --backup-dir "/path/to/backups"
```

不创建备份（不推荐）：

```bash
gps-metadata-transfer originals exports --no-backup
```

如果目标图的 EXIF 数据块损坏，允许在已备份后清除并重建 EXIF：

```bash
gps-metadata-transfer originals exports --repair-broken-exif
```

查看全部参数：

```bash
gps-metadata-transfer --help
```

## 匹配规则

不使用 `--recursive` 时，只处理两个目录的第一层。同名的 `.JPG`、`.jpg`、`.JPEG`、`.jpeg` 会被视为同一文件名。

使用 `--recursive` 时，相对路径也必须一致。例如：

```text
originals/trip/day1/IMG_001.JPG
exports/trip/day1/IMG_001.jpeg
```

如果源图没有完整的纬度和经度，工具会跳过它，不会清空目标图原有 GPS。

## 安全说明

- 工具只写目标图，不修改源图。
- 默认备份目标图；再次运行时不会覆盖旧备份，而是添加时间戳。
- 默认的 GPS 模式不会复制方向、尺寸、缩略图或像素内容。
- `--repair-broken-exif` 可能清除目标图原有 EXIF，因此只在普通写入和轻微错误重试都失败时启用，并保留备份。
- 批量处理前建议先执行 `--dry-run`，并用少量照片检查地图位置和照片方向。

## 测试

```bash
python3 -m unittest discover -s tests -v
```
