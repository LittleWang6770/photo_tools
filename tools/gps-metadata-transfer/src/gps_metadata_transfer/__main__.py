"""Allow ``python -m gps_metadata_transfer`` execution."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
