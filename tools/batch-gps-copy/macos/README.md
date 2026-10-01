# 照片 GPS 复制 · macOS App

## 使用

1. 双击项目下的 `dist/照片GPS复制.app`，也可以把它拖到「应用程序」后打开。
2. 点击「选择照片…」，通过 macOS 原生文件选择窗口选一张带完整 GPS 经纬度的 JPG/JPEG。界面会显示来源坐标；缺少 GPS 时不能开始。
3. 点击「选择文件夹…」，选择要补充或更新 GPS 的照片目录。包括其中子目录的 JPG/JPEG。
4. 选择处理方式、CPU 并发数和是否备份。
5. 点击「开始复制」。界面显示写入、跳过、失败数量以及预计剩余时间。完成后可直接打开照片目录、备份或日志。

### 写入与备份

| 选项 | 行为 |
| --- | --- |
| 跳过，不改变已有位置（默认） | 目标照片存在任意 GPS 字段就跳过；没有 GPS 的照片写入来源位置。 |
| 覆盖原图的 GPS 位置 | 无论是否已有 GPS，都写入来源经纬度与方向。 |
| 修改前备份原图（手动开启） | 将完整原文件复制到目标目录内的 `.batch-gps-copy-backup/`，保留子目录结构。重复运行遇到同名备份时追加时间戳，保留旧备份。备份失败时不修改该照片。 |
| 关闭备份（默认） | 直接更新目标照片的 GPS，不保留本次修改前的副本。 |

两种处理方式都会直接更新目标文件的元数据；「覆盖」指替换已有位置。不会重新编码 JPEG 图像。只复制经纬度和方向，不复制海拔或 GPS 时间。来源照片、隐藏文件、隐藏目录（包括备份和 `.gaze-sort`）、符号链接照片/目录不参与处理。默认不备份，关闭备份不会删除历史备份。每张照片写入后都会核验经纬度。

如需恢复，点击「打开备份」，从备份中按相对路径复制回对应照片；多次修改时选择需要恢复的版本。App 没有自动撤销功能。

CPU 选项控制同时运行的照片处理任务数，实际核心调度由 macOS 决定。自动值约为逻辑核心数的三分之一、最多 4 个；8 核机器默认为 3，可手动选择 1–8。其他机器的界面上限为逻辑核心数与 32 的较小值。

「停止」会停止安排新照片，并等待正在处理的照片完成；已经写入的 GPS 和备份保留。处理期间退出 App 也会先完成这个停止过程。剩余时间是估算，会随实际处理速度变化。

日志：`~/Library/Logs/BatchGPSCopy/app.log`，含本机运行记录及失败详情。

## 当前成品

- 版本：0.2.1，构建号 2；约 44 MiB。
- Apple Silicon / arm64，macOS 26.0 或更新版本；在 M1 Pro、macOS 27 验证。
- 内置 Python、PyObjC 和 ExifTool 13.55；运行时不依赖 Homebrew、开发虚拟环境或项目源码。
- ExifTool 使用系统 `/usr/bin/perl`，本机验证版本为 5.34。
- 使用本地 ad-hoc 签名，尚未做 Developer ID 签名或 Apple 公证，不是公开发行安装包。

## 从源码构建

在子项目根目录运行。需要 Apple Silicon Mac、Xcode Command Line Tools、Python 3.12，以及构建时使用的 ExifTool 13.55。

```bash
python3.12 -m venv .venv-app
.venv-app/bin/python -m pip install -r macos/requirements-build.txt
./macos/build_app.sh
```

构建脚本可通过 `GPS_BUILD_PYTHON=/path/to/python ./macos/build_app.sh` 使用已有构建环境。

ExifTool 可以由 Homebrew 提供，也可以把官方 13.55 发行包的目录加入 PATH。先运行 `exiftool -ver` 检查版本；构建脚本锁定经过验证的 13.55，不会自动接受其他版本。若更新 ExifTool，需更新版本检查并重新运行下面的集成测试。

构建步骤包括：从 PNG 生成各尺寸 ICNS；将 ExifTool 的纯 Perl 模块、版权说明和许可证打包到 `vendor/exiftool/`；移除 Homebrew 绝对路径；PyInstaller 打包；校验签名。可删除并重建的输出是 `build/`、`dist/`、`vendor/` 和 `.cache/`。

## 验证

```bash
PYTHONPATH=src .venv-app/bin/python -m unittest discover -s tests -v
.venv-app/bin/python macos/verify_app.py \
  --binary 'dist/照片GPS复制.app/Contents/MacOS/BatchGPSCopy' \
  --output reports/app-skip --case skip
```

另将 `--case` 分别改为 `overwrite`、`backup`、`no-backup`、`invalid`，使用不同输出目录。测试会短暂打开 App 和系统选择窗口，全部使用临时生成的 JPEG，不使用或修改用户照片。

19 项引擎测试覆盖已有 CLI 行为、停止时等待正在执行的任务、备份失败禁止写入和照片符号链接排除。五种 App 测试覆盖默认跳过且不备份、默认不备份时覆盖 GPS、手动开启备份、显式关闭备份、来源没有 GPS；核对 GPS、备份原文件哈希、来源和被跳过文件不变，以及 JPEG 图像数据和其他拍摄信息保持不变。

App 测试实际打开并取消原生照片/文件夹选择窗口，再通过相同的选择处理函数传入测试路径，触发真实「开始复制」按钮；没有模拟在 Finder 列表中逐行点击。启动时使用临时工作目录及最小 PATH，验证内置依赖可用。截图和运行日志保存在 `reports/`（不提交 Git）；0.2.1 验证结果与界面截图保存在 `artifacts/backup-2026-09-27/`，旧版验证在 `artifacts/app-2026-09-25/`。

第三方组件及许可证见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## DMG 与 GitHub Release

安装包：<https://github.com/LittleWang6770/photo_tools/releases/tag/batch-gps-copy-v0.2.1>。

打开 DMG，将左侧「照片GPS复制」拖到右侧 Applications，随后从「应用程序」启动。DMG 只有 App 和 Applications 入口，不包含照片、历史备份或开发环境。支持 Apple Silicon，macOS 26.0 及以上；尚未经过 Developer ID 签名 / Apple 公证，首次打开可能被系统提示拦截。

在已经构建并验证 App 后运行：

```bash
.venv-app/bin/python macos/build_dmg.py
```

生成 `dist/BatchGPSCopy-0.2.1-arm64.dmg` 及同名 `.dmg.sha256` 文件。脚本先检查 App 签名，设置简洁的 Finder 拖拽布局，再压缩并验证镜像；已有同名 DMG 不会被覆盖。`ds-store` 仅用于构建安装包，不进入 App 运行依赖。

Release 标签采用子项目名，例如 `batch-gps-copy-v0.2.1`；上传 DMG 与 SHA-256 校验文件。发布前需挂载只读镜像、确认包内签名及文件与原 App 一致，并用镜像中的 App 跑临时合成照片验证。
