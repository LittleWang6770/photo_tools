"""Resolve bundled resources independently of cwd, PATH and Homebrew."""
from pathlib import Path
import shutil
import sys

FROZEN = bool(getattr(sys, 'frozen', False))
ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))


def exiftool_path(requested='exiftool'):
    bundled = ROOT / 'vendor/exiftool/exiftool'
    if requested == 'exiftool' and (FROZEN or bundled.is_file()):
        if not bundled.is_file():
            raise FileNotFoundError('应用中的 ExifTool 缺失，请重新安装完整 App。')
        return str(bundled)
    found = shutil.which(requested)
    if not found:
        raise FileNotFoundError(f'找不到 ExifTool：{requested}。请安装或使用 --exiftool 指定路径。')
    return found
