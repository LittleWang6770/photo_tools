"""GUI executable, with CLI mode for reproducible packaged-engine checks."""
from pathlib import Path
import multiprocessing
import sys

if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def main():
    multiprocessing.freeze_support()
    if len(sys.argv)>1 and sys.argv[1]=='--cli':
        from batch_gps_copy.cli import main as cli
        return cli(sys.argv[2:])
    log_path=Path.home()/'Library/Logs/BatchGPSCopy/app.log'
    log_path.parent.mkdir(parents=True,exist_ok=True)
    stream=log_path.open('a',buffering=1,encoding='utf-8');sys.stdout=sys.stderr=stream
    from batch_gps_copy.gui import run
    return run(sys.argv[1:],log_path)


if __name__=='__main__':sys.exit(main() or 0)
