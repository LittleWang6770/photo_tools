from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from batch_gps_copy import cli
from test_cli import write_jpeg,set_gps


class AppEngineTests(unittest.TestCase):
    def test_default_writes_without_backups_and_preserves_old_backups_and_caches(self):
        exe=cli.exiftool_path()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'source.jpg';target=root/'target.jpg'
            preserved=[root/cli.BACKUP_DIRECTORY_NAME/'target.jpg',
                       root/'nested'/cli.BACKUP_DIRECTORY_NAME/'old.jpg',
                       root/'.gaze-sort/runs/preview.jpg']
            for p in [source,target,*preserved]:write_jpeg(p)
            set_gps(exe,source,31.,121.)
            before={p:p.read_bytes() for p in preserved}
            args=cli.build_parser().parse_args([str(source),str(root),'--exiftool',exe])
            self.assertTrue(args.no_backup)
            events=[]
            with redirect_stdout(StringIO()):self.assertEqual(cli.execute(args,events.append),0)
            self.assertEqual(events[-1]['written'],1)
            self.assertFalse(events[-1]['backup'])
            self.assertEqual(before,{p:p.read_bytes() for p in preserved})
            self.assertEqual(len(list((root/cli.BACKUP_DIRECTORY_NAME).iterdir())),1)
            metadata,_=cli.read_gps(exe,target)
            self.assertTrue(cli.has_coordinates(metadata))

    def test_default_does_not_create_backup_directory(self):
        exe=cli.exiftool_path()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'source.jpg';target=root/'target.jpg'
            write_jpeg(source);write_jpeg(target);set_gps(exe,source,31.,121.)
            args=cli.build_parser().parse_args([str(source),str(root),'--exiftool',exe])
            with redirect_stdout(StringIO()):self.assertEqual(cli.execute(args),0)
            self.assertFalse((root/cli.BACKUP_DIRECTORY_NAME).exists())

    def test_backup_switches_are_explicit_and_mutually_exclusive(self):
        parser=cli.build_parser();paths=['source.jpg','photos']
        self.assertTrue(parser.parse_args(paths).no_backup)
        self.assertTrue(parser.parse_args(paths+['--no-backup']).no_backup)
        self.assertFalse(parser.parse_args(paths+['--backup']).no_backup)
        with self.assertRaises(SystemExit):parser.parse_args(paths+['--backup','--no-backup'])

    def test_bounded_stop_drains_only_active_jobs(self):
        stop=threading.Event();calls=[]
        def work(path):
            calls.append(path.name)
            return cli.PhotoResult('written',path.name)
        results=cli.process_photos([Path(str(i)) for i in range(50)],2,work,stop)
        first=next(results);stop.set();remaining=list(results)
        self.assertEqual(len(calls),2)
        self.assertEqual([first.message]+[r.message for r in remaining],['0','1'])
        self.assertFalse(any(t.name.startswith('batch-gps-copy') for t in threading.enumerate()))

    def test_stop_before_start_does_no_work(self):
        stop=threading.Event();stop.set()
        with patch('builtins.print') as processor:
            self.assertEqual(list(cli.process_photos([Path('a')],4,processor,stop)),[])
            processor.assert_not_called()

    def test_discovery_does_not_follow_photo_symlinks(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'source.jpg';write_jpeg(source)
            (root/'alias.jpg').symlink_to(source)
            self.assertEqual(list(cli.image_files(root,source)),[])

    def test_backup_failure_prevents_writing(self):
        expected=(31.,121.,'N','E')
        with patch.object(cli,'read_gps',return_value=({},'')),patch.object(cli.shutil,'copy2',side_effect=OSError('backup failed')),patch.object(cli,'copy_gps') as write:
            with tempfile.TemporaryDirectory() as t:
                root=Path(t)
                result=cli.process_photo(root/'a.jpg',executable='exiftool',template=root/'source.jpg',
                    directory=root,backup_root=root/'backup',expected=expected,force=True,no_backup=False)
                self.assertEqual(result.status,'failed');write.assert_not_called()

    def test_callbacks_and_cancel_before_writing(self):
        exe=cli.exiftool_path()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'source.jpg';target=root/'target.jpg'
            write_jpeg(source);write_jpeg(target);set_gps(exe,source,31.,121.)
            before=target.read_bytes();stop=threading.Event();events=[]
            def event(data):
                events.append(data)
                if data['kind']=='started':stop.set()
            args=cli.build_parser().parse_args([str(source),str(root),'--exiftool',exe])
            with redirect_stdout(StringIO()):self.assertEqual(cli.execute(args,event,stop),0)
            result=events[-1]
            self.assertEqual(result['kind'],'completed');self.assertTrue(result['cancelled'])
            self.assertEqual(result['processed'],0);self.assertEqual(target.read_bytes(),before)
            self.assertFalse((root/cli.BACKUP_DIRECTORY_NAME).exists())


if __name__=='__main__':unittest.main()
