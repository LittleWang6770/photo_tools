# 全画幅等效焦段统计工具

递归读取输入路径下的 JPG/JPEG 图片，统计包含 EXIF 信息的照片数量，并按全画幅等效焦段的使用次数从高到低输出频度和占比。默认把变焦镜头产生的相近焦段归入摄影师熟悉的标准焦段。

默认隐藏占全部 EXIF 照片不足 5% 的焦段，但无论占比如何都会至少展示 Top 5；如果焦段种类少于 5，则全部展示。

## 统计口径

- 只扫描 `.jpg` 和 `.jpeg`，扩展名大小写不敏感。
- 百分比分母是“包含 EXIF 信息的图片数”，与终端总数保持一致。
- 优先读取标准 EXIF 字段 `FocalLengthIn35mmFormat`。
- 标准字段缺失时，尝试使用 ExifTool 计算的 `FocalLength35efl`。
- 默认使用 `standard` 模式，按焦段比例把 49、50、51 mm 等相近视角归入 50 mm。
- 默认标准焦段为：14、16、20、24、28、35、40、50、70、85、105、135、200、300、400、600 mm。
- `exact` 模式保留精确统计，并默认按最接近的 1 mm 分组。
- 数量相同时，焦段值较小的排在前面。
- 含 EXIF 但无法获得等效焦段的照片会计入总数，并单独报告缺失数量。
- 终端只显示归类后的焦段、照片数量和占比，不输出 `50×20` 这样的原始值明细。

例如 100 张照片包含 EXIF，其中 50 张为 35 mm、39 张为 24 mm，将显示：

```text
共有 100 张包含 EXIF 信息的图片。
 1. 35 mm：50 张，占含 EXIF 图片的 50.00%
 2. 24 mm：39 张，占含 EXIF 图片的 39.00%
```

## 环境要求

- Python 3.10 或更新版本。
- [ExifTool](https://exiftool.org/) 命令行程序。

macOS 使用 Homebrew 安装 ExifTool：

```bash
brew install exiftool
```

Ubuntu/Debian：

```bash
sudo apt install libimage-exiftool-perl
```

安装本工具：

```bash
cd tools/focal-length-statistics
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
focal-length-statistics --help
```

也可以使用 `python -m focal_length_statistics` 运行同一入口。

## 快速开始

递归统计一个照片目录：

```bash
focal-length-statistics "/path/to/photos"
```

也支持分析单张照片：

```bash
focal-length-statistics "/path/to/photo.jpg"
```

输出示例：

```text
共扫描 120 张 JPG/JPEG 图片。
共有 100 张包含 EXIF 信息的图片。
其中 96 张包含可用的全画幅等效焦段，4 张缺少该字段。

标准焦段聚类统计（按照片数量从高到低排序）：
 1. 35 mm：50 张，占含 EXIF 图片的 50.00%
 2. 24 mm：30 张，占含 EXIF 图片的 30.00%
 3. 50 mm：8 张，占含 EXIF 图片的 8.00%
 4. 85 mm：4 张，占含 EXIF 图片的 4.00%
 5. 16 mm：2 张，占含 EXIF 图片的 2.00%
```

## 自定义显示规则

### 聚类模式

默认的标准焦段聚类：

```bash
focal-length-statistics "/path/to/photos" --grouping standard
```

使用自定义标准焦段：

```bash
focal-length-statistics "/path/to/photos" \
  --grouping standard \
  --anchors 24,28,35,50,70,85,135,200
```

归类使用对称的比例距离，而不是绝对毫米差。例如 49 mm 和 51 mm 都最接近 50 mm。所有照片会被分配给距离最近的标准焦段。

如果需要查看原始焦段分布，可以切换到精确模式：

```bash
focal-length-statistics "/path/to/photos" --grouping exact
```

精确模式默认以 1 mm 为间隔分组，也可以改为 0.5 mm：

```bash
focal-length-statistics "/path/to/photos" --grouping exact --bucket-size 0.5
```

### 显示阈值

把占比阈值改为 3%，并至少显示 Top 10：

```bash
focal-length-statistics "/path/to/photos" \
  --minimum-percentage 3 \
  --minimum-items 10
```

如果 ExifTool 不在 `PATH` 中：

```bash
focal-length-statistics "/path/to/photos" \
  --exiftool "/custom/path/exiftool"
```

查看全部参数：

```bash
focal-length-statistics --help
```

## 性能说明

工具只调用一次 ExifTool 批量读取元数据，不会逐张启动外部进程。它不会解码图片像素，也不会修改任何照片。

## 测试

安装为 editable package 后运行：

```bash
python -m unittest discover -s tests -v
```
