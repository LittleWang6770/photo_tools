# Photo Tools

两个相互独立、可直接从命令行使用的照片工具：

- [`exif_transfer_project/`](exif_transfer_project/)：把原图中的 GPS 经纬度（可选全部拍摄 EXIF）迁移到导出图。
- [`photo_compress/`](photo_compress/)：批量压缩 JPEG/PNG，支持输出到新目录或显式原地压缩。

每个工具都有独立的依赖说明、完整用法和安全注意事项，请进入对应目录阅读 README。

## 设计原则

- 所有输入路径和运行参数都通过 CLI 传入，不在源码中保存本机路径。
- 默认选择可恢复的行为：EXIF 修改前备份；压缩优先输出到新目录。
- 写文件时先生成并校验临时文件，再原子替换，避免中断留下半成品。
- 本地照片、虚拟环境、日志、断点文件不会提交到 Git。

## 快速检查

```bash
python3 -m unittest discover -s exif_transfer_project/tests -v
python3 -m unittest discover -s photo_compress/tests -v
```
