"""Allow ``python -m photo_compressor`` execution."""

import multiprocessing

from .cli import main


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
