# 照片批量压缩工具

递归压缩 JPEG 和 PNG，并尽量保留 EXIF、ICC、DPI、PNG 文本信息、文件时间、权限和 macOS 扩展属性。所有输出都先写入临时文件，重新打开校验成功后再原子替换。

工具提供两种模式：

- `--output`：写入新目录，推荐且最安全。
- `--in-place`：只在结果确实更小时原地替换；必须显式启用，并建议提前备份。

## 特性

- JPEG 有损压缩，默认质量 `88`；PNG 无损重新压缩。
- 默认递归保留子目录结构。
- 输出模式默认跳过已有文件，支持中断后重跑。
- 原地模式使用断点记录，避免 JPEG 被意外重复压缩。
- 压缩结果不比原图小时，输出模式复制原图，原地模式保持原图不动。
- 动画 PNG/APNG 默认跳过，防止动画帧丢失。
- 支持并行处理、低 CPU 调度优先级、小批量试跑和 CSV 日志。

## 安装

需要 Python 3.10 或更新版本。

```bash
cd tools/photo-compressor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
photo-compressor --help
```

Windows 激活虚拟环境：

```powershell
.venv\Scripts\activate
```

也可以使用 `python -m photo_compressor` 运行同一入口。

## 推荐用法：输出到新目录

先扫描并预览，不写文件：

```bash
photo-compressor "/path/to/originals" \
  --output "/path/to/compressed" \
  --dry-run
```

先试跑 100 张：

```bash
photo-compressor "/path/to/originals" \
  --output "/path/to/compressed" \
  --limit 100
```

确认画质、方向、色彩和定位信息无误后处理全部照片：

```bash
photo-compressor "/path/to/originals" \
  --output "/path/to/compressed"
```

输出目录会保留输入目录的层级。已存在的目标文件默认跳过；如确实需要重新生成：

```bash
photo-compressor "/path/to/originals" \
  --output "/path/to/compressed" \
  --overwrite
```

## 原地压缩

原地压缩会修改照片，请先准备独立备份，并先执行小批量试跑：

```bash
photo-compressor "/path/to/photos" --in-place --limit 100
```

确认无误后处理剩余照片：

```bash
photo-compressor "/path/to/photos" --in-place
```

断点文件 `.photo-compress-state.jsonl` 和日志 `photo-compress-log.csv` 默认保存在照片根目录。断点记录包含压缩参数签名、文件大小和修改时间；参数或文件发生变化后会重新处理。

仅在明确需要时忽略断点记录：

```bash
photo-compressor "/path/to/photos" --in-place --force
```

JPEG 是有损格式，`--force` 可能造成重复压缩和累积画质损失。

## 画质和格式

JPEG 默认质量是 `88`。更保守可设为 `90`，更节省空间可尝试 `85`：

```bash
photo-compressor "/path/to/originals" \
  --output "/path/to/compressed" \
  --quality 90
```

只处理 JPEG 或 PNG：

```bash
photo-compressor "/path/to/originals" \
  --output "/path/to/compressed" \
  --format jpeg

photo-compressor "/path/to/originals" \
  --output "/path/to/compressed" \
  --format png
```

PNG 压缩是无损的，不缩小尺寸、不减少颜色、不删除透明通道。默认压缩等级为 `9`。

## 性能预设

默认 `--profile balanced` 使用 4 个进程。可根据磁盘选择：

| 预设 | 进程数 | 建议场景 |
| --- | ---: | --- |
| `balanced` | 4 | SSD，速度和前台使用体验平衡 |
| `light` | 2 | SSD，希望更低负载和发热 |
| `hdd` | 1 | 同一块机械硬盘读写，减少随机寻道 |

示例：

```bash
photo-compressor "/path/to/originals" \
  --output "/path/to/compressed" \
  --profile hdd
```

也可以用 `--workers 3` 覆盖预设。默认 `--nice 10` 会降低工作进程的 CPU 优先级；不希望降低时使用 `--nice 0`。

## 日志与返回码

每次运行会生成 UTF-8 CSV 日志，记录相对路径、格式、处理状态、前后大小、耗时、参数签名和错误。

- 输出模式：日志默认在输出目录。
- 原地模式：日志默认在输入目录。
- 可用 `--log-file "/path/to/log.csv"` 自定义。

全部处理成功时返回码为 `0`；任意图片失败时返回码为 `1`；命令参数错误时返回码为 `2`。

查看全部参数：

```bash
photo-compressor --help
```

## 安全说明

- 输出目录不能等于输入目录，也不能位于输入目录内部，以免递归处理输出结果。
- 临时文件与目标文件位于同一目录，校验通过后才使用 `os.replace` 原子替换。
- 原地模式只有在新文件体积更小时才替换原图。
- APNG 会被跳过，因为普通 Pillow 保存流程无法保留完整动画。
- 图片元数据由 Pillow 尽力保留；对重要档案照片，仍应保留原始文件并抽样核对 EXIF、色彩、透明度和方向。

## 测试

```bash
python -m unittest discover -s tests -v
```
