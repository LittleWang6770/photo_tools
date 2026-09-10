"""Allow ``python -m focal_length_statistics`` execution."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
