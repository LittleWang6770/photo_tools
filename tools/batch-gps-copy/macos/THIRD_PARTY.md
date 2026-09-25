# 第三方组件

- [ExifTool 13.55](https://github.com/exiftool/exiftool)：Phil Harvey 等贡献者，按 Perl 相同条款提供（Artistic License 或 GNU GPL）。App 内置上游 README、`perlartistic.pod`、`perlgpl.pod` 与 `provenance.json`，位于 `Contents/Resources/vendor/exiftool/`。只调整解释器路径和模块搜索路径，使其独立于构建机的 Homebrew 安装位置；未修改 GPS 处理模块。
- [Python 3.12](https://www.python.org/)：PSF License；随 PyInstaller 的 Python framework 一起打包。
- [PyObjC 12.2.2](https://github.com/ronaldoussoren/pyobjc)：MIT License；用于 Cocoa 原生窗口及控件。
- [PyInstaller 6.22.3](https://github.com/pyinstaller/pyinstaller)：GPL，包含允许分发所构建应用的 bootloader 例外；用于构建独立 App。

Python、PyObjC 和 PyInstaller 的许可证文本包含在 `Contents/Resources/licenses/`。本项目没有把系统 Perl 或 macOS Cocoa 框架复制进 App；运行时使用操作系统提供的版本。构建依赖版本见 `requirements-build.txt`。
