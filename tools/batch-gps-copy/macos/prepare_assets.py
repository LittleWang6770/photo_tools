"""Create icon sizes and relocate the installed pure-Perl ExifTool distribution."""
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import re
import shutil
import subprocess
import sysconfig

ROOT=Path(__file__).resolve().parents[1]


def main():
    iconset=ROOT/'build/icon/GPSCopy.iconset';iconset.mkdir(parents=True,exist_ok=True)
    source=ROOT/'macos/assets/gps-copy.png'
    for size in (16,32,128,256,512):
        for scale in (1,2):
            name=f'icon_{size}x{size}'+('@2x' if scale==2 else '')+'.png'
            subprocess.run(['/usr/bin/sips','-z',str(size*scale),str(size*scale),str(source),'--out',str(iconset/name)],check=True,capture_output=True)
    subprocess.run(['/usr/bin/iconutil','-c','icns',str(iconset),'-o',str(ROOT/'macos/assets/GPSCopy.icns')],check=True)
    executable=shutil.which('exiftool')
    if not executable:raise RuntimeError('构建时需要 ExifTool：brew install exiftool')
    executable=Path(executable).resolve()
    version=subprocess.check_output([str(executable),'-ver'],text=True).strip()
    if version!='13.55':raise RuntimeError(f'此构建验证过 ExifTool 13.55，当前 {version}；请先验证新版本再更新构建锁定。')
    locations=[executable.parent/'lib',executable.parent.parent/'libexec/lib/perl5']
    library=next((p for p in locations if (p/'Image/ExifTool.pm').is_file()),None)
    if library is None:raise RuntimeError('无法定位 ExifTool 的 Perl 模块')
    vendor=ROOT/'vendor/exiftool'
    if vendor.exists():shutil.rmtree(vendor)
    (vendor/'lib/File').mkdir(parents=True)
    shutil.copytree(library/'Image',vendor/'lib/Image')
    shutil.copyfile(library/'File/RandomAccess.pm',vendor/'lib/File/RandomAccess.pm')
    original=executable.read_text()
    script=re.sub(r'^#![^\n]+','#!/usr/bin/perl',original,count=1)
    script=re.sub(r'^unshift @INC, "[^\n]*?/libexec/lib/perl5[^\n]*";\n','',script,flags=re.M)
    if 'unshift @INC, $incDir;' not in script:
        script=script.replace('    # load or disable config file if specified','    unshift @INC, $incDir;\n\n    # load or disable config file if specified',1)
    if '/opt/homebrew/' in script or '/usr/local/Cellar/' in script:raise RuntimeError('ExifTool 尚有构建机依赖')
    (vendor/'exiftool').write_text(script);(vendor/'exiftool').chmod(0o755)
    readme=next((p for p in [executable.parent/'README',executable.parent.parent/'README'] if p.is_file()),None)
    if readme is None:raise RuntimeError('缺少 ExifTool 上游版权说明')
    shutil.copyfile(readme,vendor/'README')
    for name in ['perlartistic','perlgpl']:
        license_path=Path('/System/Library/Perl/5.34/pods')/(name+'.pod')
        if not license_path.exists():raise RuntimeError('找不到 Perl 许可证文本：'+str(license_path))
        shutil.copyfile(license_path,vendor/(name+'.pod'))
    manifest={'version':version,'upstream':'https://github.com/exiftool/exiftool',
              'modifications':'Relocate Homebrew library paths to adjacent lib; use /usr/bin/perl.',
              'installed_script_sha256':hashlib.sha256(original.encode()).hexdigest(),
              'bundled_script_sha256':hashlib.sha256(script.encode()).hexdigest()}
    (vendor/'provenance.json').write_text(json.dumps(manifest,indent=2)+'\n')
    licenses=ROOT/'vendor/licenses';licenses.mkdir(parents=True,exist_ok=True)
    python_license=Path(sysconfig.get_path('stdlib'))/'LICENSE.txt'
    shutil.copyfile(python_license,licenses/'Python-LICENSE.txt')
    for package,filename,target in [
        ('pyobjc-framework-Cocoa','LICENSE.txt','PyObjC-LICENSE.txt'),
        ('pyinstaller','COPYING.txt','PyInstaller-COPYING.txt'),
    ]:
        installed=distribution(package)
        relative=next(p for p in installed.files if p.name==filename and 'licenses' in p.parts)
        shutil.copyfile(installed.locate_file(relative),licenses/target)
    shutil.copyfile(ROOT/'macos/THIRD_PARTY.md',licenses/'THIRD_PARTY.md')
    result=subprocess.check_output(['/usr/bin/perl',str(vendor/'exiftool'),'-config','','-ver'],
                                   env={'PATH':'/usr/bin:/bin'},text=True).strip()
    assert result==version
    print('图标及便携 ExifTool 已准备：',version)


if __name__=='__main__':main()
