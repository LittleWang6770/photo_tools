"""Native picker/button tests on generated JPEG fixtures; no user photos."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from batch_gps_copy.cli import read_gps,run_exiftool,coordinate_values
from batch_gps_copy.runtime import exiftool_path
from test_cli import write_jpeg,set_gps


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case',choices=['skip','overwrite','backup','no-backup','invalid'],default='skip')
    args=parser.parse_args();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
    exe=exiftool_path()
    with tempfile.TemporaryDirectory(prefix='gps-app-test-') as temporary:
        root=Path(temporary);folder=root/'照片 with spaces';folder.mkdir()
        source=folder/'来源照片.JPG';blank=folder/'无位置.JPG';existing=folder/'已有位置.jpeg';nested=folder/'子目录/第二张.jpg'
        photos=[source,blank,existing,nested]
        for p in photos:write_jpeg(p)
        ignored=[folder/'.gaze-sort/runs/preview.jpg',folder/'.cache/thumb.jpg']
        for p in ignored:write_jpeg(p)
        ignored_before={p:sha(p) for p in ignored}
        if args.case!='invalid':set_gps(exe,source,-33.5,-70.6)
        set_gps(exe,existing,31.2304,121.4737)
        for p in [blank,existing,nested]:
            result=run_exiftool(exe,['-Artist=GPS App Test','-DateTimeOriginal=2026:09:25 12:34:56','-overwrite_original',str(p)])
            assert result.returncode==0
        before={p.relative_to(folder).as_posix():sha(p) for p in photos}
        pixels={p.name:hashlib.sha256(p.read_bytes()[p.read_bytes().index(b'\xff\xda'):]).hexdigest() for p in photos}
        config={'template':str(source),'directory':str(folder),'force':args.case=='overwrite',
                'workers':1 if args.case=='skip' else min(2,os.cpu_count() or 1),
                'output':str(args.output)}
        # Default cases must exercise the untouched checkbox, not set it off.
        if args.case in ['backup','no-backup']:config['backup']=args.case=='backup'
        config_path=root/'test.json';config_path.write_text(json.dumps(config))
        # An app launched from Finder cannot rely on the developer's brew PATH.
        env=dict(os.environ,PATH='/usr/bin:/bin',PYTHONPATH='')
        with (args.output/'launch.log').open('w') as stream:
            subprocess.run([str(args.binary.resolve()),'--ui-smoke',str(config_path)],cwd=root,env=env,
                           stdout=stream,stderr=subprocess.STDOUT,timeout=120,check=True)
        receipt=json.loads((args.output/'gui-test.json').read_text())
        assert receipt['initial_backup'] is False
        assert ignored_before=={p:sha(p) for p in ignored}
        assert receipt['panels']=={'photo':{'native':True,'files':True,'directories':False,'multiple':False},
                                   'directory':{'native':True,'files':False,'directories':True,'multiple':False}}
        assert sha(source)==before[source.name]
        if args.case=='invalid':
            assert not receipt['template_valid'] and not receipt['run_enabled'] and receipt['result'] is None
            assert before=={p.relative_to(folder).as_posix():sha(p) for p in photos}
            assert not (folder/'.batch-gps-copy-backup').exists()
        else:
            expected_written=3 if args.case=='overwrite' else 2
            result=receipt['result']
            assert result['total']==3 and result['processed']==3 and result['written']==expected_written
            assert result['failed']==0 and not result['cancelled']
            assert result['skipped']==3-expected_written
            assert receipt['run_options']=={'force':config['force'],'backup':config.get('backup',False),'workers':config['workers']}
            assert result['backup']==config.get('backup',False)
            assert ('已保留备份' if result['backup'] else '本次未生成原图备份') in receipt['status']
            for p in [blank,existing,nested]:
                gps,error=read_gps(exe,p);assert gps is not None,error
                expected=(31.2304,121.4737,'N','E') if p==existing and args.case!='overwrite' else (33.5,70.6,'S','W')
                actual=coordinate_values(gps)
                assert actual[2:]==expected[2:] and all(abs(a-b)<1e-7 for a,b in zip(actual[:2],expected[:2]))
                metadata=json.loads(run_exiftool(exe,['-j','-Artist','-DateTimeOriginal',str(p)]).stdout)[0]
                assert metadata['Artist']=='GPS App Test' and metadata['DateTimeOriginal']=='2026:09:25 12:34:56'
                assert hashlib.sha256(p.read_bytes()[p.read_bytes().index(b'\xff\xda'):]).hexdigest()==pixels[p.name]
            if args.case!='overwrite':assert sha(existing)==before[existing.name]
            backup=folder/'.batch-gps-copy-backup'
            if config.get('backup',False):
                originals=[p for p in backup.rglob('*') if p.is_file()]
                assert len(originals)==expected_written
                assert all(sha(p)==before[p.relative_to(backup).as_posix()] for p in originals)
            else:assert not backup.exists()
            result.pop('backup_directory')
        receipt.update(case=args.case,template_unchanged=True,backup_content_verified=True,hidden_caches_unchanged=True,
                       jpeg_scan_and_non_gps_metadata_preserved=True,minimal_path_launch=True)
        (args.output/'validation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
        print('PASS:',args.case,'native pickers, controls, GPS, original backups and unchanged image data')


if __name__=='__main__':main()
