"""Build a minimal drag-to-Applications DMG from an already verified app."""
import argparse
import hashlib
from pathlib import Path
import plistlib
import subprocess
import tempfile

from ds_store import DSStore


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=root/'dist/照片GPS复制.app')
    parser.add_argument('--output', type=Path, help='DMG output path; existing files are never overwritten')
    args = parser.parse_args()
    app = args.app.resolve()
    info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
    version = info['CFBundleShortVersionString']
    output = (args.output or root/f'dist/BatchGPSCopy-{version}-arm64.dmg').resolve()
    if output.exists():
        parser.error(f'输出已存在，未覆盖：{output}')
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='gps-dmg-stage-') as temporary:
        stage = Path(temporary)
        subprocess.run(['/usr/bin/ditto', str(app), str(stage/app.name)], check=True)
        (stage/'Applications').symlink_to('/Applications', target_is_directory=True)
        with DSStore.open(str(stage/'.DS_Store'), 'w+') as store:
            store['.']['bwsp'] = {'ShowToolbar': False, 'ShowStatusBar': False,
                                 'ShowPathbar': False, 'ShowSidebar': False,
                                 'ContainerShowSidebar': False, 'SidebarWidth': 0,
                                 'WindowBounds': '{{240, 180}, {560, 320}}'}
            store['.']['icvp'] = {'viewOptionsVersion': 1, 'backgroundType': 1,
                                 'backgroundColorRed': .965, 'backgroundColorGreen': .978,
                                 'backgroundColorBlue': .977, 'iconSize': 96., 'textSize': 14.,
                                 'gridSpacing': 100., 'gridOffsetX': 0., 'gridOffsetY': 0.,
                                 'labelOnBottom': True, 'showItemInfo': False,
                                 'showIconPreview': False, 'arrangeBy': 'none'}
            store['.']['vstl'] = ('type', b'icnv')
            store['.']['vSrn'] = ('long', 1)
            store[app.name]['Iloc'] = (140, 140)
            store['Applications']['Iloc'] = (420, 140)
        subprocess.run(['/usr/bin/hdiutil', 'create', '-volname', '照片 GPS 复制',
                        '-fs', 'HFS+', '-format', 'UDZO', '-srcfolder', str(stage),
                        str(output)], check=True)
    subprocess.run(['/usr/bin/hdiutil', 'verify', str(output)], check=True)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    checksum_path = output.with_suffix(output.suffix+'.sha256')
    checksum_path.write_text(f'{checksum}  {output.name}\n')
    print(output)
    print(checksum_path)


if __name__ == '__main__':
    main()
