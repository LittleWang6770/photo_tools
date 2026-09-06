# 批量复制照片 GPS

把一张 JPG/JPEG 模板照片中的 GPS 经纬度和南北/东西方向标记，递归复制到指定文件夹内的所有 JPG/JPEG 照片。海拔、GPS 时间等其他定位字段不会被复制。

- 目标照片已有任何 GPS 信息时默认跳过。
- 使用 `-f` 或 `--force` 强制覆盖已有 GPS。
- 写入后自动核验经纬度。
- 修改前默认将原文件备份到目标文件夹内的 `.batch-gps-copy-backup/`；重复运行不会覆盖旧备份。
- 模板照片即使位于目标文件夹内也不会被处理。

## 安装

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

如明确不需要备份：

```bash
batch-gps-copy -f --no-backup target_photo.JPG /path/to/photos
```

工具只处理 `.jpg` 和 `.jpeg`（扩展名大小写不敏感），并递归处理子文件夹。模板照片必须包含完整的 GPS 纬度和经度，否则工具会拒绝运行。

## 测试

```bash
python3 -m unittest discover -s tests -v
```
