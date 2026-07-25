# Photo Tools

`photo-tools` 是一个多工具仓库，包含三个相互独立、可直接安装的命令行工具：

- [`tools/gps-metadata-transfer/`](tools/gps-metadata-transfer/)：把原图中的 GPS 经纬度（可选全部拍摄 EXIF）迁移到导出图。
- [`tools/photo-compressor/`](tools/photo-compressor/)：批量压缩 JPEG/PNG，支持输出到新目录或显式原地压缩。
- [`tools/focal-length-statistics/`](tools/focal-length-statistics/)：递归统计 JPG/JPEG 的全画幅等效焦段使用频度。

每个工具都有独立的依赖说明、完整用法和安全注意事项，请进入对应目录阅读 README。

## 设计原则

- 所有输入路径和运行参数都通过 CLI 传入，不在源码中保存本机路径。
- 默认选择可恢复的行为：EXIF 修改前备份；压缩优先输出到新目录。
- 写文件时先生成并校验临时文件，再原子替换，避免中断留下半成品。
- 本地照片、虚拟环境、日志、断点文件不会提交到 Git。

## 命名与目录约定

三个工具遵循相同的现代 Python 项目结构：

```text
tools/<project-name>/
├── pyproject.toml
├── README.md
├── src/<package_name>/
│   ├── __init__.py
│   ├── __main__.py
│   └── cli.py
└── tests/
    └── test_cli.py
```

- 项目目录和终端命令使用 `kebab-case`，例如 `photo-compressor`。
- Python 包使用 `snake_case`，例如 `photo_compressor`。
- `cli.py` 集中当前小工具的命令行编排和业务流程；功能增长后可按领域继续拆分模块。
- `__main__.py` 统一支持 `python -m <package_name>` 运行方式。
- 依赖、Python 版本和命令入口统一声明在 `pyproject.toml`。

## 快速检查

```bash
tools/gps-metadata-transfer/.venv/bin/python -m unittest discover \
  -s tools/gps-metadata-transfer/tests -v

tools/photo-compressor/.venv/bin/python -m unittest discover \
  -s tools/photo-compressor/tests -v

tools/focal-length-statistics/.venv/bin/python -m unittest discover \
  -s tools/focal-length-statistics/tests -v
```
