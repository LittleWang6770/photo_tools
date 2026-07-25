from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

try:
    from exif_transfer_project import exif_transfer
except ModuleNotFoundError:  # 允许从工具目录直接运行测试
    import exif_transfer


class DiscoverPairsTests(unittest.TestCase):
    def test_matches_case_insensitive_extensions_and_stems(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "IMG_001.JPG").write_bytes(b"source")
            (target / "img_001.jpeg").write_bytes(b"target")

            pairs, warnings = exif_transfer.discover_pairs(source, target, recursive=False)

            self.assertEqual(1, len(pairs))
            self.assertEqual([], warnings)
            self.assertEqual("img_001.jpeg", pairs[0].relative_target.as_posix())

    def test_recursive_mode_requires_matching_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            (source / "day1").mkdir(parents=True)
            (target / "day1").mkdir(parents=True)
            (target / "day2").mkdir(parents=True)
            (source / "day1" / "a.jpg").write_bytes(b"source")
            (target / "day1" / "a.jpeg").write_bytes(b"target")
            (target / "day2" / "a.jpeg").write_bytes(b"target")

            pairs, warnings = exif_transfer.discover_pairs(source, target, recursive=True)

            self.assertEqual(["day1/a.jpeg"], [pair.relative_target.as_posix() for pair in pairs])
            self.assertEqual(1, len(warnings))


class MetadataHelpersTests(unittest.TestCase):
    def test_numeric_values_use_tolerance(self) -> None:
        self.assertTrue(exif_transfer.values_equal(31.23456780, 31.23456781))
        self.assertFalse(exif_transfer.values_equal(31.2, 31.3))

    def test_gps_match_ignores_tags_missing_from_source(self) -> None:
        source = {"GPSLatitude": 31.2, "GPSLongitude": 121.5}
        target = {
            "GPSLatitude": 31.2,
            "GPSLongitude": 121.5,
            "GPSAltitude": 30,
        }
        self.assertTrue(exif_transfer.gps_matches(source, target))
        target["GPSLongitude"] = 120.0
        self.assertFalse(exif_transfer.gps_matches(source, target))

    def test_gps_copy_does_not_include_dimensions(self) -> None:
        arguments = exif_transfer.copy_arguments(
            Path("source.jpg"), Path("target.jpg"), all_exif=False
        )
        self.assertIn("-GPS:All", arguments)
        self.assertNotIn("-IFD0:All", arguments)

    def test_all_exif_excludes_orientation_and_dimensions(self) -> None:
        arguments = exif_transfer.copy_arguments(
            Path("source.jpg"), Path("target.jpg"), all_exif=True
        )
        self.assertIn("-IFD0:All", arguments)
        self.assertIn("Orientation", arguments)
        self.assertIn("ImageWidth", arguments)

    def test_backup_never_overwrites_previous_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "target.jpg"
            target.write_bytes(b"target")
            pair = exif_transfer.PhotoPair(Path("source.jpg"), target, Path("target.jpg"))
            backup_root = root / "backup"

            first = exif_transfer.create_backup(pair, backup_root)
            second = exif_transfer.create_backup(pair, backup_root)

            self.assertNotEqual(first, second)
            self.assertEqual(b"target", first.read_bytes())
            self.assertEqual(b"target", second.read_bytes())


class CommandLineTests(unittest.TestCase):
    def test_dry_run_does_not_require_exiftool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.jpg"
            target = root / "target.jpg"
            source.write_bytes(b"not-an-image")
            target.write_bytes(b"not-an-image")
            output = io.StringIO()

            with redirect_stdout(output):
                return_code = exif_transfer.main(
                    [str(source), str(target), "--dry-run", "--exiftool", "missing"]
                )

            self.assertEqual(0, return_code)
            self.assertIn("未修改文件", output.getvalue())


if __name__ == "__main__":
    unittest.main()
