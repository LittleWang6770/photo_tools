#!/bin/sh
set -eu
GPS_PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$GPS_PROJECT_DIR"
GPS_BUILD_PYTHON=${GPS_BUILD_PYTHON:-"$GPS_PROJECT_DIR/.venv-app/bin/python"}
if [ ! -x "$GPS_BUILD_PYTHON" ]; then
    echo '请按 macos/README.md 创建 .venv-app 构建环境。' >&2
    exit 1
fi
if [ -d /Library/Developer/CommandLineTools ]; then
    export DEVELOPER_DIR=/Library/Developer/CommandLineTools
fi
export PYINSTALLER_CONFIG_DIR="$GPS_PROJECT_DIR/.cache/pyinstaller"
"$GPS_BUILD_PYTHON" macos/prepare_assets.py
"$GPS_BUILD_PYTHON" -m PyInstaller --noconfirm --distpath dist --workpath build/app macos/BatchGPSCopy.spec
/usr/bin/codesign --verify --deep --strict 'dist/照片GPS复制.app'
echo "已生成：$GPS_PROJECT_DIR/dist/照片GPS复制.app"
