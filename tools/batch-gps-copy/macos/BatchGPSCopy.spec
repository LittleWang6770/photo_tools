from pathlib import Path

root=Path(SPECPATH).parent
a=Analysis([str(root/'macos/app.py')],pathex=[str(root/'src')],
    datas=[(str(root/'vendor/exiftool'),'vendor/exiftool'),
           (str(root/'vendor/licenses'),'licenses'),
           (str(root/'macos/assets/gps-copy.png'),'assets')],
    binaries=[],hiddenimports=['AppKit','Foundation','objc','batch_gps_copy.gui'],
    excludes=['tkinter','torch','numpy','PIL','matplotlib','IPython'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='BatchGPSCopy',
    console=False,strip=False,upx=False,target_arch='arm64',codesign_identity=None)
collection=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='BatchGPSCopy')
app=BUNDLE(collection,name='照片GPS复制.app',icon=str(root/'macos/assets/GPSCopy.icns'),
    bundle_identifier='com.littlewang.batch-gps-copy',info_plist={
        'CFBundleName':'照片GPS复制','CFBundleDisplayName':'照片 GPS 复制',
        'CFBundleShortVersionString':'0.2.0','CFBundleVersion':'1',
        'NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication',
        'LSMinimumSystemVersion':'26.0','CFBundleDevelopmentRegion':'zh_CN',
        'NSDesktopFolderUsageDescription':'读取所选来源照片，并为目标照片写入 GPS 和保存原图备份。',
        'NSDocumentsFolderUsageDescription':'读取所选来源照片，并为目标照片写入 GPS 和保存原图备份。',
        'NSDownloadsFolderUsageDescription':'读取所选来源照片，并为目标照片写入 GPS 和保存原图备份。',
        'NSRemovableVolumesUsageDescription':'处理所选磁盘中的照片并保留修改前备份。'})
